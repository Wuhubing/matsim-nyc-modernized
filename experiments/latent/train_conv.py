#!/usr/bin/env python3
"""Predict the stable-state plan from a person's day and the city structure (docs/converged-plan-plan.md, step 3).

  train_conv.py SAMPLES.npz --static static.npz --city city.npz --out DIR [--versions ...] [--runs 3]
                [--extern NAME=PROBS.npz ...]

Network: city structure (road per cell, rail / bus departures per cell and hour, hour embedding) -> linear -> two
rounds of mean message passing -> E[cell, hour] (as train4.py). Trip token: origin and destination activity,
departure hour, departure / 24, log1p straight-line km, trip index, E[origin, hour], E[destination, hour], their
product, and (unless no_init) the initial plan's mode -> linear -> 2-layer Transformer over the person's day, with a
subpopulation token; person vector z = mean of the day. Head per trip on [token, z]: main-mode logits (8) and
departure-shift logits (17 quarter-hour bins, -2..+2 h). Loss: cross-entropy on seed 4711's labels (soft: the
iteration 80/90/100 mode counts) + 0.5 x shift cross-entropy (+ 0.5 x congestion regression with 'aux': E -> log
of seed 4711's mean road congestion per cell and hour). Early stopping on the validation persons' mode log loss.

Versions: full; no_init (no initial mode); no_city (E depends on the hour only); no_context (each trip alone:
no Transformer, no subpopulation, no day); cell_table (learned per-cell table instead of structure); aux; soft;
combinations joined by '+', e.g. 'no_init+no_city'.
Persons: train crc32 % 10 >= 2, validation == 0, never trained == 1 ('unseen'). Test against seeds 4712 and 4713.

Evaluation (same code for everything, so every number uses one definition): per-trip accuracy and log loss of the
mode; per origin cell (>= 50 labelled trips) root mean square difference of the expected car and pt share from the
labels' shares, all persons and the related cohort; departure shift within one quarter hour. References evaluated
the same way: seed 4711's labels as a prediction (the cross-seed yardstick U), the initial plan's mode, and lookups
of seed 4711's training persons by (subpopulation, origin and destination activity) and additionally distance band;
plus any --extern probabilities ([n, T, 8], e.g. gradient boosting)."""
import argparse, json, time
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn

M, B = 8, 17
CAR, PT = 0, 3


class Net(nn.Module):
    def __init__(self, opts, road, transit, adj, n_cells):
        super().__init__()
        self.o = opts
        self.register_buffer('road', road); self.register_buffer('transit', transit)
        A = torch.zeros(n_cells, n_cells)
        if len(adj): A[adj[:, 0], adj[:, 1]] = 1
        self.register_buffer('A', A / A.sum(1, keepdim=True).clamp(min=1))
        self.hour = nn.Embedding(30, 16); self.act = nn.Embedding(6, 8); self.mode = nn.Embedding(M, 8); self.sub = nn.Embedding(3, 64)
        self.s_in = nn.Linear(8 + 2 + 16, 32); self.s_mp = nn.ModuleList([nn.Linear(64, 32) for _ in range(2)])
        self.table = nn.Parameter(torch.zeros(n_cells + 1, 30, 32)); self.hour_only = nn.Parameter(torch.zeros(30, 32))
        self.tok_in = nn.Linear(8 * 2 + 16 + 3 + 32 * 3 + 8, 64)
        self.enc = nn.TransformerEncoder(nn.TransformerEncoderLayer(64, 4, 128, 0.1, batch_first=True), 2)
        self.solo = nn.Sequential(nn.Linear(64, 64), nn.ReLU(), nn.Linear(64, 64))
        self.head = nn.Sequential(nn.Linear(128, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, M + B))
        self.cong = nn.Linear(32, 1)

    def city(self):
        C1 = self.road.shape[0]
        if 'no_city' in self.o: return self.hour_only.unsqueeze(0).expand(C1, -1, -1)
        if 'cell_table' in self.o: return self.table
        h = self.hour.weight.unsqueeze(0).expand(C1 - 1, -1, -1)
        e = torch.relu(self.s_in(torch.cat([self.road[:-1].unsqueeze(1).expand(-1, 30, -1), self.transit[:-1], h], -1)))
        for m in self.s_mp:
            e = e + torch.relu(m(torch.cat([e, torch.einsum('ij,jhd->ihd', self.A, e)], -1)))
        return torch.cat([e, torch.zeros(1, 30, 32, device=e.device)], 0)

    def forward(self, tok, x, init, sub, E=None):
        E = self.city() if E is None else E
        pad = tok[..., 0] < 0; t = tok.clamp(min=0).long()
        h, o, d = t[..., 2], t[..., 3], t[..., 4]
        eo, ed = E[o, h], E[d, h]
        im = self.mode(init.clamp(min=0).long()) * (0.0 if 'no_init' in self.o else 1.0)
        z = self.tok_in(torch.cat([self.act(t[..., 0]), self.act(t[..., 1]), self.hour(h), x, eo, ed, eo * ed, im], -1))
        if 'no_context' in self.o:
            y = self.solo(z); zp = torch.zeros_like(y)
        else:
            s = self.sub(sub.long()).unsqueeze(1)
            p2 = torch.cat([torch.zeros_like(pad[:, :1]), pad], 1)
            y = self.enc(torch.cat([s, z], 1), src_key_padding_mask=p2)[:, 1:]
            m = (~pad).float().unsqueeze(-1); zp = ((y * m).sum(1) / m.sum(1).clamp(min=1)).unsqueeze(1).expand_as(y)
        out = self.head(torch.cat([y, zp], -1))
        return out[..., :M], out[..., M:]


def evaluate(P, label, D, persons):
    """P [n, T, M] probabilities; label [n, T] modes (-1 unusable); D sample arrays; persons bool [n]."""
    valid = (label >= 0) & persons[:, None]
    lab = label[valid].astype(int); p = np.clip(P[valid], 1e-6, 1)
    r = {'trips': int(valid.sum()), 'acc': float((p.argmax(1) == lab).mean()), 'logloss': float(-np.log(p[np.arange(len(lab)), lab]).mean())}
    for g, keep in (('all', np.ones(len(persons), bool)), ('related', D['related'])):
        v = valid & keep[:, None]; cells = D['tok'][..., 3][v]
        n = np.bincount(cells, minlength=int(D['n_cells']))
        for k, name in ((CAR, 'car'), (PT, 'pt')):
            pred = np.bincount(cells, P[v][:, k], minlength=len(n)); true = np.bincount(cells, label[v] == k, minlength=len(n))
            ok = n >= 50
            r[f'cell_rmse_{name}_{g}'] = float(np.sqrt(np.mean((pred[ok] / n[ok] - true[ok] / n[ok]) ** 2)))
    return r


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('samples')
    for k in ('--static', '--city', '--out'): ap.add_argument(k, required=True)
    ap.add_argument('--versions', default='full,no_init,no_city,no_context,cell_table,aux,soft,no_init+no_city,no_init+no_context')
    ap.add_argument('--runs', type=int, default=3); ap.add_argument('--epochs', type=int, default=40); ap.add_argument('--patience', type=int, default=5)
    ap.add_argument('--extern', nargs='*', default=[])
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    D = dict(np.load(a.samples)); Z = np.load(a.static); C = np.load(a.city)
    n_cells = len(C['cells']); n = len(D['sub'])
    grp = D['grp']; tr, va = np.nonzero(grp >= 2)[0], np.nonzero(grp == 0)[0]
    groups = {'all': np.ones(n, bool), 'seen': grp >= 2, 'unseen': grp == 1}
    print(f'device {dev}; persons {n}; train {len(tr)}, val {len(va)}, unseen {groups["unseen"].sum()}', flush=True)
    # congestion target for 'aux': seed 4711 baseline states, observed cell-hours
    X = C['X']; base = [i for i, s in enumerate(C['states']) if s.startswith('4711-')]
    obs = (X[base, :, :, 2].mean(0) > 0.5); cong_t = torch.tensor(np.log(np.clip(X[base, :, :, 1].mean(0), 0.5, 5)), device=dev)
    obs_t = torch.tensor(obs, device=dev)
    T = {k: torch.as_tensor(D[k], device=dev) for k in ('tok', 'x', 'init', 'sub')}
    T['tok'] = T['tok'].long(); T['init'] = T['init'].long()
    hard = torch.as_tensor(D['mode_4711'], device=dev).long(); shift = torch.as_tensor(D['shift_4711'], device=dev).long()
    soft = torch.as_tensor(D['soft_4711'], device=dev)
    results = {'references': {}, 'versions': {}}

    def score(name, P, store):
        r = {}
        for s in (4712, 4713):
            for g, pm in groups.items(): r[f'{s}_{g}'] = evaluate(P, D[f'mode_{s}'], D, pm)
        store[name] = r
        print(name, json.dumps({k: {m: round(v, 4) for m, v in x.items() if m in ('acc', 'logloss', 'cell_rmse_car_all', 'cell_rmse_pt_all', 'cell_rmse_car_related')}
                                for k, x in r.items() if k.endswith('_all') or k.endswith('_unseen')}), flush=True)

    onehot = lambda L: np.eye(M, dtype=np.float32)[np.clip(L, 0, M - 1)] * (L >= 0)[..., None] + (L < 0)[..., None] / M
    score('seed 4711 labels (cross-seed U)', onehot(D['mode_4711']), results['references'])
    score('initial plan mode', onehot(D['init']), results['references'])
    valid = D['tok'][..., 0] >= 0
    dband = np.minimum(np.floor(np.log2(np.maximum(np.expm1(D['x'][..., 1]), 0.25) / 0.25)).astype(int), 8)   # as ceiling.py
    keys = {'purpose': np.stack([np.broadcast_to(D['sub'][:, None], valid.shape), D['tok'][..., 0], D['tok'][..., 1]], -1),
            'purpose and distance': np.stack([np.broadcast_to(D['sub'][:, None], valid.shape), D['tok'][..., 0], D['tok'][..., 1], dband], -1)}
    for name, K in keys.items():
        code = np.ravel_multi_index(tuple(np.clip(K[..., i], 0, None) for i in range(K.shape[-1])), tuple(int(K[..., i].max()) + 1 for i in range(K.shape[-1])))
        use = valid & (D['mode_4711'] >= 0) & (grp >= 2)[:, None]
        cnt = np.zeros((code.max() + 1, M)); np.add.at(cnt, (code[use], D['mode_4711'][use]), 1)
        cnt += 0.5; P = cnt[code] / cnt[code].sum(-1, keepdims=True)
        score(f'lookup by {name}', P.astype(np.float32), results['references'])
    for e in a.extern:
        name, path = e.split('=', 1); score(name, np.load(path)['P'], results['references'])
    with open(out / 'results.json', 'w') as f: json.dump(results, f, indent=1)

    road = torch.tensor(Z['road']); transit = torch.tensor(Z['transit']); adj = torch.tensor(C['adj'], dtype=torch.long)
    ce = nn.CrossEntropyLoss(ignore_index=-1)

    def predict(model, idx):
        model.eval(); outp = np.zeros((len(idx), D['tok'].shape[1], M), np.float32)
        with torch.no_grad():
            E = model.city()
            for i in range(0, len(idx), 4096):
                j = idx[i:i + 4096]
                lm, _ = model(T['tok'][j], T['x'][j], T['init'][j], T['sub'][j], E)
                outp[i:i + len(j)] = torch.softmax(lm, -1).cpu().numpy()
        return outp

    def val_loss(model):
        P = predict(model, va); L = D['mode_4711'][va]; v = L >= 0
        return float(-np.log(np.clip(P[v][np.arange(v.sum()), L[v]], 1e-6, 1)).mean())

    for version in a.versions.split(','):
        opts = set(version.split('+')); results['versions'][version] = {}; preds = []
        for run in range(a.runs):
            torch.manual_seed(run); np.random.seed(run)
            model = Net(opts, road, transit, adj, n_cells).to(dev)
            opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
            best, best_state, bad, t0 = 1e9, None, 0, time.time()
            for ep in range(a.epochs):
                model.train()
                perm = np.random.permutation(tr)
                for i in range(0, len(perm), 512):
                    j = torch.as_tensor(perm[i:i + 512], device=dev)
                    lm, ls = model(T['tok'][j], T['x'][j], T['init'][j], T['sub'][j])
                    if 'soft' in opts:
                        tgt = soft[j]; w = tgt.sum(-1) > 0
                        loss = -(torch.log_softmax(lm, -1)[w] * (tgt[w] / tgt[w].sum(-1, keepdim=True))).sum(-1).mean()
                    else:
                        loss = ce(lm.reshape(-1, M), hard[j].reshape(-1))
                    loss = loss + 0.5 * ce(ls.reshape(-1, B), shift[j].reshape(-1))
                    if 'aux' in opts:
                        E = model.city()[:-1]; loss = loss + 0.5 * ((model.cong(E).squeeze(-1) - cong_t) ** 2)[obs_t].mean()
                    opt.zero_grad(); loss.backward(); opt.step()
                v = val_loss(model)
                print(f'{version} run {run} epoch {ep}: val mode log loss {v:.4f} ({time.time() - t0:.0f}s)', flush=True)
                if v < best - 1e-4: best, bad, best_state = v, 0, {k: t.detach().clone() for k, t in model.state_dict().items()}
                else:
                    bad += 1
                    if bad >= a.patience: break
            model.load_state_dict(best_state)
            preds.append(predict(model, np.arange(n)))
            torch.save(model.state_dict(), out / f'{version}-{run}.pt')
        score(f'{version} (ensemble of {a.runs})', np.mean(preds, 0), results['versions'])
        score(f'{version} (run 0)', preds[0], results['versions'])
        with open(out / 'results.json', 'w') as f: json.dump(results, f, indent=1)
    print('done', flush=True)


if __name__ == '__main__':
    main()
