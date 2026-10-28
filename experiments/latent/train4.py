#!/usr/bin/env python3
"""Baseline pretraining of a city + agent network and a toll adapter (docs/policy-prediction-plan.md, steps 4-5).

  train4.py pretrain SAMPLES.npz --city city.npz --transit T1.npz T2.npz --static static.npz --links links.pkl
            --out DIR [--versions struct_own,...] [--runs 3]
  train4.py adapt SAMPLES.npz ... --out DIR [--runs 3]
  train4.py diagnose SAMPLES.npz ... --out DIR      (after pretrain and adapt)

Task as in train.py (new plan executed better than its parent; time and route near ties |label| <= 1 dropped),
with its trip-level pairing, innovation type and auxiliary regression. Inputs that do not depend on a run:
- city structure: per cell road km, lane km, capacity, free speed, fast share, links, position (static.npz road)
  and per cell and hour scheduled rail and bus stop departures (static.npz transit), with an hour embedding ->
  linear -> two rounds of mean message passing over the 8-neighbourhood -> E[cell, hour];
- the person's own day: activities of the initial plan (type, E at its cell and start hour, start, end, duration)
  -> 2-layer Transformer -> mean, with subpopulation and number of trips -> z.
Optional run state ('state': road congestion of k-1 and transit waits of k-10 as in train.py, added to E;
'memory': the stored-plan tokens of train.py, pooled next to the own day) and cell identity ('cellid': a learned
embedding per cell in plan and activity tokens). Versions (VERSIONS): struct_own (structure + own day, the one the
adapter builds on), v3 (state + memory + cell identity: train.py's third version), all (structure + own day +
state + memory), no_city (E = learned per-hour vector: no cell information anywhere), no_agent (structure; z from
subpopulation and trips only), cell_table (E = learned per-cell table instead of structure, + own day); the
'_notrip' variants also drop the router's planned travel time, route length and legs from the trips, which
otherwise already carry what the network structure does for a trip.

Toll adapter (zero when the toll is zero, so the baseline is unchanged): per trip tolled links crossed, dollars and
money utility x dollars -> linear without bias -> added to the plan token; per cell and hour log1p(tolled links x
price) -> small MLP -> E * (1 + gamma) + beta, scaled by (toll > 0). 'adapt' starts from the pretrained
struct_own runs and trains on schema1 seed 4711 (val = crc32 % 10 == 0): none (no training), toll_only (frozen
network; only a weight on money utility x (toll of the new plan - toll of the parent) and a bias added to the
logit: the score already contains -money utility x toll, so this is what plain arithmetic gets), adapter (only the
adapter), adapter_10 (adapter, 10% of the training samples), finetune (everything, lr 3e-4), scratch and
scratch_10 (a new network with the adapter, everything trained on schema1 only / on the same 10%). Tests: schema2
seed 4712 (new price and seed), schema1 seed 4712 (new seed), baseline seed 4712.
People with crc32 % 10 == 1 are never trained on (either stage); every report also gives the AUC on them
('unseen_*'), so memorising a person's day does not count.

'diagnose' checks the pipeline: the AUC function against a brute-force pairwise count; what the trained
struct_own runs rely on (test AUC on baseline seed 4712 when, at test time only, the city vectors are shuffled
across cells or averaged over cells, the own-day tokens or the parent scores or the innovation types are shuffled
across samples, or the router's trip times are zeroed); the adapter and toll_only refitted and evaluated on the
schema2 samples whose new or parent plan crosses a toll link (the other ~95% cannot show a toll effect); a ridge
probe, cross-validated over cells, of whether the learned city vectors predict the baseline's observed congestion
per cell and hour better than the raw road and transit features."""
import argparse, json, pickle, time
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
from train import auc

KINDS = ['mode', 'time', 'route']
VERSIONS = {'struct_own': {'struct', 'own'}, 'v3': {'state', 'memory', 'cellid'}, 'all': {'struct', 'own', 'state', 'memory'},
            'no_city': {'no_city', 'own'}, 'no_agent': {'struct', 'no_agent'}, 'cell_table': {'cell_table', 'own'}}
VERSIONS.update({f'{k}_notrip': v | {'notrip'} for k, v in list(VERSIONS.items())})
PEAK = [0.0, 9.18, 14.0]
D = 64


def hour_price(peak):
    h = np.arange(30)
    return np.where(((6 <= h) & (h < 10)) | ((14 <= h) & (h < 20)), peak, 3.06 if peak else 0.0)


class Net(nn.Module):
    def __init__(self, opts, road, transit, adj, toll_cells, X_state, n_cells):
        super().__init__()
        self.o = opts
        self.register_buffer('road', road); self.register_buffer('transit', transit)
        self.register_buffer('Xs', X_state); self.register_buffer('toll_cells', toll_cells)
        A = torch.zeros(n_cells, n_cells)
        if len(adj): A[adj[:, 0], adj[:, 1]] = 1
        self.register_buffer('A', A / A.sum(1, keepdim=True).clamp(min=1))
        self.hour = nn.Embedding(32, 16); self.mode = nn.Embedding(9, 16); self.act = nn.Embedding(7, 8)
        self.cell = nn.Embedding(n_cells + 1, 16); self.kind = nn.Embedding(3, 8)
        self.s_in = nn.Linear(8 + 2 + 16, 32); self.s_mp = nn.ModuleList([nn.Linear(64, 32) for _ in range(2)])
        self.x_in = nn.Linear(7 + 16, 32); self.x_mp = nn.ModuleList([nn.Linear(64, 32) for _ in range(2)])
        self.table = nn.Parameter(torch.zeros(n_cells + 1, 30, 32)); self.hour_only = nn.Parameter(torch.zeros(30, 32))
        layer = lambda: nn.TransformerEncoder(nn.TransformerEncoderLayer(D, 4, 128, 0.1, batch_first=True), 2)
        self.plan_in = nn.Linear(16 * 4 + 8 * 2 + 4 + 64 + 16 + 4 + 4 + 1, D); self.plan_enc = layer()
        self.own_in = nn.Linear(8 + 16 + 32 + 3, D); self.own_enc = layer()
        self.mem_in = nn.Linear(17, D); self.mem_enc = layer()
        self.agent_out = nn.Sequential(nn.Linear(2 * D + 7, D), nn.ReLU(), nn.Linear(D, D))
        self.agent_small = nn.Sequential(nn.Linear(4, D), nn.ReLU(), nn.Linear(D, D))
        self.head = nn.Sequential(nn.Linear(6 * D + 1 + 8, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, 2))
        # toll adapter
        self.toll_tok = nn.Linear(3, D, bias=False); nn.init.zeros_(self.toll_tok.weight)
        self.film = nn.Sequential(nn.Linear(1, 16), nn.ReLU(), nn.Linear(16, 64)); nn.init.zeros_(self.film[2].weight); nn.init.zeros_(self.film[2].bias)
        self.toll_logit = nn.Parameter(torch.zeros(2))                # toll_only control: weight, bias (bias used only when trained)

    def adapter_parameters(self): return list(self.toll_tok.parameters()) + list(self.film.parameters())

    def mp(self, e, layers):
        for m in layers:
            nb = torch.einsum('ij,...jhd->...ihd', self.A, e)
            e = e + torch.relu(m(torch.cat([e, nb], -1)))
        return e

    def city(self):
        """E per scenario [3, C+1, 30, 32] (structure; the 'other' cell is zero) and the state part [S, C+1, 30, 32]."""
        C1 = self.road.shape[0]
        if 'no_city' in self.o: E = self.hour_only.unsqueeze(0).expand(C1, -1, -1)
        elif 'cell_table' in self.o: E = self.table
        elif 'struct' in self.o:
            h = self.hour.weight[:30].unsqueeze(0).expand(C1 - 1, -1, -1)
            x = torch.cat([self.road[:-1].unsqueeze(1).expand(-1, 30, -1), self.transit[:-1], h], -1)
            E = torch.cat([self.mp(torch.relu(self.s_in(x)), self.s_mp), torch.zeros(1, 30, 32, device=x.device)], 0)
        else: E = torch.zeros(C1, 30, 32, device=self.road.device)
        Es = []
        for sc in range(3):
            t = self.toll_cells * torch.as_tensor(hour_price(PEAK[sc]), dtype=torch.float32, device=E.device)  # [C+1, 30]
            f = self.film(torch.log1p(t).unsqueeze(-1)) * (t > 0).float().unsqueeze(-1)
            Es.append(E * (1 + f[..., :32]) + f[..., 32:])
        state = None
        if 'state' in self.o:
            S = self.Xs.shape[0]
            h = self.hour.weight[:30].view(1, 1, 30, 16).expand(S, self.Xs.shape[1], -1, -1)
            e = self.mp(torch.relu(self.x_in(torch.cat([self.Xs, h], -1))), self.x_mp)
            state = torch.cat([e, torch.zeros_like(e[:, :1])], 1)
        return torch.stack(Es), state

    def cities(self, Eall, state, b):
        """Per-sample lookup function (cell, hour) -> E."""
        sc, st = b['scen'], b['state']
        def look(c, h):
            e = Eall[sc.view(-1, *([1] * (c.dim() - 1))), c, h]
            if state is not None: e = e + state[st.view(-1, *([1] * (c.dim() - 1))), c, h]
            return e
        return look

    def plan(self, tok, f, otok, of, toll, look):
        pad = tok[..., 0] < 0; pad[:, 0] = False
        t = tok.clamp(min=0).long(); ot = otok.clamp(min=0).long()
        o, d, hr = t[..., 2], t[..., 3], t[..., 1]
        f = f.clone(); of = of.clone(); f[..., 0] = f[..., 0] / 24; of[..., 0] = of[..., 0] / 24
        if 'notrip' in self.o: f[..., 1:] = 0; of[..., 1:] = 0
        other = torch.cat([self.mode(ot[..., 0]), of, f - of, (t[..., 0] != ot[..., 0]).float().unsqueeze(-1)], -1)
        cid = 'cellid' in self.o
        co, cd = (self.cell(o), self.cell(d)) if cid else (torch.zeros(*o.shape, 16, device=o.device),) * 2
        x = torch.cat([self.mode(t[..., 0]), self.hour(hr), co, cd, self.act(t[..., 4]), self.act(t[..., 5]), f,
                       look(o, hr), look(d, hr), other], -1)
        x = self.plan_in(x) + self.toll_tok(toll)
        return self.plan_enc(x, src_key_padding_mask=pad), pad

    @staticmethod
    def pool(x, pad):
        m = (~pad).float().unsqueeze(-1); return (x * m).sum(1) / m.sum(1).clamp(min=1)

    def agent(self, b, look):
        if 'no_agent' in self.o: return self.agent_small(b['summ'][:, :4])
        parts = []
        if 'own' in self.o:
            tok = b['ag_tok']; pad = tok[..., 0] < 0; pad[:, 0] = False
            t = tok.clamp(min=0).long(); hr = (b['ag_x'][..., 0] * 24).long().clamp(0, 29)
            cid = self.cell(t[..., 1]) if ('cellid' in self.o) else torch.zeros(*t.shape[:2], 16, device=t.device)
            x = self.own_enc(self.own_in(torch.cat([self.act(t[..., 0]), cid, look(t[..., 1], hr), b['ag_x']], -1)),
                             src_key_padding_mask=pad)
            parts.append(self.pool(x, pad))
        else: parts.append(torch.zeros(b['summ'].shape[0], D, device=b['summ'].device))
        if 'memory' in self.o:
            pad = b['mem'].abs().sum(-1) == 0; pad[:, 0] = False
            parts.append(self.pool(self.mem_enc(self.mem_in(b['mem']), src_key_padding_mask=pad), pad))
            summ = b['summ']
        else:
            parts.append(torch.zeros_like(parts[0])); summ = torch.cat([b['summ'][:, :4], torch.zeros_like(b['summ'][:, 4:])], -1)
        return self.agent_out(torch.cat(parts + [summ], -1))

    def forward(self, b, city=None):
        Eall, state = city if city is not None else self.city()
        look = self.cities(Eall, state, b)
        lam = b['lam'].view(-1, 1, 1)
        tn = torch.cat([b['new_toll'], b['new_toll'][..., 1:] * lam], -1); tp = torch.cat([b['par_toll'], b['par_toll'][..., 1:] * lam], -1)
        xn, pn = self.plan(b['new'], b['new_x'], b['par'], b['par_x'], tn, look)
        xp, pp = self.plan(b['par'], b['par_x'], b['new'], b['new_x'], tp, look)
        hn, hp = self.pool(xn, pn), self.pool(xp, pp)
        z = self.agent(b, look)
        out = self.head(torch.cat([z, hn, hp, z * hn, z * hp, hn - hp, b['par_score'].unsqueeze(-1), self.kind(b['kind'])], -1))
        du = (tn[..., 2].sum(1) - tp[..., 2].sum(1))                # money utility x dollars / 10, new - parent
        return out + torch.stack([self.toll_logit[0] * du + self.toll_logit[1], torch.zeros_like(du)], -1)


def diagnose(a, out, dev, S, C, make, arrays, y, sel, seen, val, seed, scen, predict, report, fit):
    res = {}
    # 1. AUC against a brute-force pairwise count (ties count one half)
    rng = np.random.default_rng(0); sc = np.round(rng.normal(size=1500), 1); yy = rng.random(1500) < 0.4
    pos, neg = sc[yy], sc[~yy]
    brute = ((pos[:, None] > neg[None]).sum() + 0.5 * (pos[:, None] == neg[None]).sum()) / (len(pos) * len(neg))
    res['auc_check'] = {'auc': auc(sc, yy), 'brute_force': float(brute)}
    print('auc check', res['auc_check'], flush=True)

    def load(run):
        model = make(VERSIONS['struct_own']); model.load_state_dict(torch.load(out / f'struct_own-{run}.pt', map_location=dev)); return model

    # 2. what the trained struct_own runs rely on (test-time perturbations, baseline seed 4712)
    te = sel((scen == 0) & (seed == 4712)); perm = rng.permutation(len(te))
    cell_perm = lambda n: torch.cat([torch.randperm(n - 1, generator=torch.Generator().manual_seed(0)), torch.tensor([n - 1])])
    zero_router = lambda v: np.concatenate([v[..., :1], 0 * v[..., 1:]], -1)
    tests = {
        'none': ({}, None),
        'city shuffled across cells': ({}, lambda E, st: (E[:, cell_perm(E.shape[1]).to(E.device)], st)),
        'city averaged over cells': ({}, lambda E, st: (torch.cat([E[:, :-1].mean(1, keepdim=True).expand(-1, E.shape[1] - 1, -1, -1), E[:, -1:]], 1), st)),
        'own day shuffled': ({'ag_tok': lambda v: v[perm], 'ag_x': lambda v: v[perm]}, None),
        'router trip times zeroed': ({'new_x': zero_router, 'par_x': zero_router}, None),
        'parent score shuffled': ({'par_score': lambda v: v[perm]}, None),
        'innovation type shuffled': ({'kind': lambda v: v[perm]}, None),
    }
    res['reliance'] = {}
    for name, (chg, cchg) in tests.items():
        vals = []
        for run in range(a.runs):
            model = load(run); saved = {}
            for k, f in chg.items(): saved[k] = arrays[k]; arrays[k] = arrays[k].copy(); arrays[k][te] = f(arrays[k][te])
            if cchg is not None:
                orig = model.city; model.city = lambda orig=orig: cchg(*orig())
            vals.append(report(predict(model, te), te)); arrays.update(saved)
        res['reliance'][name] = {k: float(np.mean([v[k] for v in vals])) for k in ('all', 'mode', 'time', 'route', 'unseen_all')}
        print('reliance', name, {k: round(v, 4) for k, v in res['reliance'][name].items()}, flush=True)

    # 3. adapter vs toll_only vs none on toll-affected schema2 samples
    crossing = (S['new_toll'][:, :, 0].sum(1) + S['par_toll'][:, :, 0].sum(1)) > 0
    tr_all, va = sel((scen == 1) & (seed == 4711) & ~val & seen), sel((scen == 1) & (seed == 4711) & val)
    aff = sel((scen == 2) & (seed == 4712) & crossing)
    res['toll_affected'] = {'n': int(len(aff)), 'better_share': float(y[aff].mean())}
    for variant in ('none', 'toll_only', 'adapter', 'finetune'):
        vals = []
        for run in range(a.runs):
            torch.manual_seed(run); model = load(run)
            if variant == 'toll_only':
                for p in model.parameters(): p.requires_grad = False
                model.toll_logit.requires_grad = True; fit(model, tr_all, va, [model.toll_logit], 1e-2, f'diag {variant} {run}')
            elif variant == 'adapter':
                for p in model.parameters(): p.requires_grad = False
                for p in model.adapter_parameters(): p.requires_grad = True
                fit(model, tr_all, va, model.adapter_parameters(), 1e-3, f'diag {variant} {run}')
            elif variant == 'finetune':
                fit(model, tr_all, va, [p for n, p in model.named_parameters() if n != 'toll_logit'], 3e-4, f'diag {variant} {run}')
            vals.append(report(predict(model, aff), aff))
        res['toll_affected'][variant] = {k: float(np.nanmean([v[k] for v in vals])) for k in ('all', 'mode', 'mode_related', 'time', 'route')}
        print('toll-affected schema2', variant, {k: round(v, 4) for k, v in res['toll_affected'][variant].items()}, flush=True)

    # 4. ridge probe: do the learned city vectors predict observed baseline congestion per cell and hour?
    X = C['X']; cong = X[..., 1].mean(0); obs = X[..., 2].mean(0) > 0.5           # baseline states only, [C, 30]
    Z = np.load(a.static); n = cong.shape[0]
    hour = np.broadcast_to(np.eye(30), (n, 30, 30))
    raw = np.concatenate([np.repeat(Z['road'][:n, None], 30, 1), Z['transit'][:n], hour], -1)
    model = load(0); model.eval()
    with torch.no_grad(): E = model.city()[0][0, :n].cpu().numpy()
    t = np.log(np.clip(cong, 0.5, 5))
    def probe(F):
        F = F.reshape(n, 30, -1); folds = np.arange(n) % 5; pred = np.zeros((n, 30))
        for f in range(5):
            trn = (folds != f)[:, None] & obs; tst = (folds == f)[:, None] & obs
            A = np.concatenate([F[trn], np.ones((trn.sum(), 1))], 1); w = np.linalg.solve(A.T @ A + 1e-2 * np.eye(A.shape[1]), A.T @ t[trn])
            pred[tst] = np.concatenate([F[tst], np.ones((tst.sum(), 1))], 1) @ w
        r = t[obs] - pred[obs]; return float(1 - (r ** 2).sum() / ((t[obs] - t[obs].mean()) ** 2).sum())
    res['probe_r2'] = {'hour only': probe(hour), 'raw road + transit + hour': probe(raw), 'learned city vectors E': probe(E),
                       'E + raw': probe(np.concatenate([E, raw], -1))}
    print('probe R2 (log congestion, 5-fold over cells)', res['probe_r2'], flush=True)
    with open(out / 'diagnose.json', 'w') as f: json.dump(res, f, indent=1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('stage', choices=['pretrain', 'adapt', 'diagnose']); ap.add_argument('samples')
    for k in ('--city', '--static', '--links', '--out'): ap.add_argument(k, required=True)
    ap.add_argument('--transit', nargs='+', required=True)
    ap.add_argument('--versions', default='struct_own,v3,all,no_city,no_agent,cell_table')
    ap.add_argument('--runs', type=int, default=3); ap.add_argument('--epochs', type=int, default=30); ap.add_argument('--patience', type=int, default=4)
    ap.add_argument('--clear', type=float, default=1.0)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    S = np.load(a.samples); C = np.load(a.city); Z = np.load(a.static)
    n_cells = len(C['cells'])
    # run state as in train.py
    X = torch.tensor(C['X']); X[..., 0] = X[..., 0] / 5; X[..., 1] = X[..., 1].clamp(max=5) - 1
    tstate = {}
    for path in a.transit:
        T = np.load(path); tstate.update({n: T['T'][i] for i, n in enumerate(T['states'])})
    TX = torch.tensor(np.stack([tstate[f"{n.split('-')[0]}-{int(n.split('-')[1]) + 1 - 10}"] for n in C['states']]))
    TX[..., 0] = TX[..., 0] / 5; TX[..., 1] = TX[..., 1] / 10
    Xs = torch.cat([X, TX], -1)
    with open(a.links, 'rb') as f: L = pickle.load(f)
    toll_cells = np.zeros((n_cells + 1, 1), np.float32)
    for c, ff, t in L.values():
        if t: toll_cells[c if c >= 0 else n_cells, 0] += 1
    toll_cells[n_cells] = 0
    road = torch.tensor(Z['road']); transit = torch.tensor(Z['transit'])
    adj = torch.tensor(C['adj'], dtype=torch.long)
    make = lambda opts: Net(opts, road, transit, adj, torch.tensor(toll_cells), Xs, n_cells).to(dev)

    keep = (S['kind'] == 0) | (np.abs(S['label']) > a.clear)
    seed, val, scen = S['seed'], S['val'].astype(bool), S['scen']
    ps = S['par_score'].astype(np.float32); base_tr = keep & (scen == 0) & (seed == 4711) & ~val
    mu, sd = ps[base_tr].mean(), ps[base_tr].std() + 1e-6
    summ = S['summ'].astype(np.float32).copy(); smu, ssd = summ[base_tr].mean(0), summ[base_tr].std(0) + 1e-6
    summ[:, 3:7] = (summ[:, 3:7] - smu[3:7]) / ssd[3:7]
    mem = S['mem'].astype(np.float32).copy(); mem[..., 8] = np.clip(mem[..., 8] / 10, -10, 10)
    nt = S['new_toll'].astype(np.float32).copy(); pt = S['par_toll'].astype(np.float32).copy()
    nt[..., 1] /= 10; pt[..., 1] /= 10                               # dollars / 10
    charged = (S['scen'] > 0).astype(np.float32)[:, None]           # crossings count only where a toll is charged,
    nt[..., 0] *= charged; pt[..., 0] *= charged                     # so the adapter is exactly zero on the baseline
    arrays = {'new': S['new'], 'new_x': S['new_x'], 'par': S['par'], 'par_x': S['par_x'], 'mem': mem, 'summ': summ,
              'par_score': (ps - mu) / sd, 'state': S['state'], 'scen': scen, 'kind': S['kind'], 'new_toll': nt,
              'par_toll': pt, 'lam': S['lam'].astype(np.float32) * 10, 'ag_tok': S['ag_tok'], 'ag_x': S['ag_x']}
    LONG = ('new', 'par', 'state', 'scen', 'kind', 'ag_tok')
    y = (S['label'] > 0).astype(np.float32); yr = np.clip(S['label'] / 10, -5, 5).astype(np.float32)
    kind, rel = S['kind'], S['related'].astype(bool)
    unseen = S['grp'] == 1
    print(f'device {dev}; samples by scenario {np.bincount(scen)}; kept {keep.sum()}', flush=True)

    def batches(idx, bs, shuffle):
        if shuffle: idx = np.random.permutation(idx)
        for i in range(0, len(idx), bs):
            j = idx[i:i + bs]
            b = {k: torch.as_tensor(v[j], device=dev) for k, v in arrays.items()}
            for k in LONG: b[k] = b[k].long()
            yield b, j

    def predict(model, idx):
        model.eval(); outp = np.empty(len(idx), np.float32); pos = 0
        with torch.no_grad():
            city = model.city()
            for b, j in batches(idx, 4096, False):
                outp[pos:pos + len(j)] = model(b, city)[:, 0].float().cpu().numpy(); pos += len(j)
        return outp

    def report(score, idx):
        r = {'n': int(len(idx))}
        for pre, sub in (('', np.ones(len(idx), bool)), ('unseen_', unseen[idx])):
            r[f'{pre}all'] = auc(score[sub], y[idx][sub])
            for k, name in enumerate(KINDS):
                m = (kind[idx] == k) & sub; r[f'{pre}{name}'] = auc(score[m], y[idx][m])
                r[f'{pre}{name}_related'] = auc(score[m & rel[idx]], y[idx][m & rel[idx]])
        return r

    def fit(model, tr, va, params, lr, tag):
        opt = torch.optim.AdamW(params, lr=lr, weight_decay=1e-4)
        bce, huber = nn.BCEWithLogitsLoss(), nn.HuberLoss()
        best, best_state, bad, t0 = -1, None, 0, time.time()
        for ep in range(a.epochs):
            model.train()
            for b, j in batches(tr, 512, True):
                o = model(b)
                loss = bce(o[:, 0], torch.as_tensor(y[j], device=dev)) + 0.5 * huber(o[:, 1], torch.as_tensor(yr[j], device=dev))
                opt.zero_grad(); loss.backward(); opt.step()
            v = auc(predict(model, va), y[va])
            print(f'{tag} epoch {ep}: val AUC {v:.4f} ({time.time() - t0:.0f}s)', flush=True)
            if v > best + 1e-4: best, bad, best_state = v, 0, {k: t.detach().clone() for k, t in model.state_dict().items()}
            else:
                bad += 1
                if bad >= a.patience: break
        model.load_state_dict(best_state)
        return best, ep + 1

    sel = lambda m: np.nonzero(m & keep)[0]
    seen = ~unseen                                                  # training and validation never use group 1
    results = {}
    if a.stage == 'pretrain':
        tr, va, te = sel((scen == 0) & (seed == 4711) & ~val & seen), sel((scen == 0) & (seed == 4711) & val), sel((scen == 0) & (seed == 4712))
        for version in a.versions.split(','):
            opts = VERSIONS[version]; results[version] = {'runs': []}; preds = []
            for run in range(a.runs):
                torch.manual_seed(run); np.random.seed(run)
                model = make(opts)
                best, eps = fit(model, tr, va, [p for n, p in model.named_parameters() if not n.startswith(('toll_tok', 'film', 'toll_logit'))], 1e-3, f'{version} run {run}')
                p = predict(model, te); preds.append(p)
                r = report(p, te); r.update(val_auc=best, epochs=eps); results[version]['runs'].append(r)
                print(f'{version} run {run} test', json.dumps(r), flush=True)
                if version == 'struct_own': torch.save(model.state_dict(), out / f'struct_own-{run}.pt')
            results[version]['ensemble'] = report(np.mean(preds, 0), te)
            print(f'{version} ensemble', json.dumps(results[version]['ensemble']), flush=True)
            with open(out / 'pretrain.json', 'w') as f: json.dump(results, f, indent=1)
    elif a.stage == 'adapt':
        tr_all, va = sel((scen == 1) & (seed == 4711) & ~val & seen), sel((scen == 1) & (seed == 4711) & val)
        rng = np.random.default_rng(0); tr10 = np.sort(rng.choice(tr_all, len(tr_all) // 10, replace=False))
        tests = {'schema2_s4712': sel((scen == 2) & (seed == 4712)), 'schema1_s4712': sel((scen == 1) & (seed == 4712)),
                 'baseline_s4712': sel((scen == 0) & (seed == 4712))}
        print({k: len(v) for k, v in tests.items()}, 'train', len(tr_all), flush=True)
        opts = VERSIONS['struct_own']
        for variant in ('none', 'toll_only', 'adapter', 'adapter_10', 'finetune', 'scratch', 'scratch_10'):
            results[variant] = {'runs': []}; preds = {t: [] for t in tests}
            for run in range(a.runs):
                torch.manual_seed(run); np.random.seed(run)
                model = make(opts)
                if not variant.startswith('scratch'): model.load_state_dict(torch.load(out / f'struct_own-{run}.pt', map_location=dev))
                if variant == 'toll_only':
                    for p in model.parameters(): p.requires_grad = False
                    model.toll_logit.requires_grad = True
                    fit(model, tr_all, va, [model.toll_logit], 1e-2, f'{variant} run {run}')
                    print('toll_only weight, bias', model.toll_logit.detach().cpu().tolist(), flush=True)
                elif variant in ('adapter', 'adapter_10'):
                    for p in model.parameters(): p.requires_grad = False
                    for p in model.adapter_parameters(): p.requires_grad = True
                    fit(model, tr_all if variant == 'adapter' else tr10, va, model.adapter_parameters(), 1e-3, f'{variant} run {run}')
                elif variant == 'finetune': fit(model, tr_all, va, [p for n, p in model.named_parameters() if n != 'toll_logit'], 3e-4, f'{variant} run {run}')
                elif variant.startswith('scratch'):
                    fit(model, tr_all if variant == 'scratch' else tr10, va, [p for n, p in model.named_parameters() if n != 'toll_logit'], 1e-3, f'{variant} run {run}')
                r = {}
                for t, idx in tests.items():
                    p = predict(model, idx); preds[t].append(p); r[t] = report(p, idx)
                results[variant]['runs'].append(r)
                print(f'{variant} run {run}', json.dumps({t: {k: round(v, 4) for k, v in x.items() if k in ('all', 'mode', 'mode_related')} for t, x in r.items()}), flush=True)
            results[variant]['ensemble'] = {t: report(np.mean(preds[t], 0), idx) for t, idx in tests.items()}
            print(f'{variant} ensemble', json.dumps(results[variant]['ensemble']), flush=True)
            with open(out / 'adapt.json', 'w') as f: json.dump(results, f, indent=1)
    else:
        diagnose(a, out, dev, S, C, make, arrays, y, sel, seen, val, seed, scen, predict, report, fit)
    print('done', flush=True)


if __name__ == '__main__':
    main()
