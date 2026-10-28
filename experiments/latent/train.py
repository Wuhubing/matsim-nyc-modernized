#!/usr/bin/env python3
"""City latent + agent latent network and its ablations (docs/latent-choice-plan.md, step 5).

  train.py SAMPLES.npz CITY.npz --out RESULTS.json [--versions full,no_city,no_agent] [--runs 2]

Task: P(executed score of the innovated plan > stored score of its parent), from information available before
iteration k. Train on seed 4711 (val = crc32(person) % 10 == 0), test on seed 4712 (same sampled agents).
- city encoder: per state, cell and hour (log entries, congestion, observed) -> linear -> two rounds of mean
  message passing over the cell 8-neighbourhood -> E[state, cell, hour]; 'no_city' replaces E by a learned table
  that does not depend on the state;
- plan encoder: per trip mode, departure hour, origin/destination cell and activity, E at origin and destination
  -> 2-layer Transformer -> mean -> h; shared by the new and the parent plan;
- agent encoder: activities of the parent plan (type, cell, end hour) -> 2-layer Transformer -> mean, with the
  memory summary -> z; 'no_agent' keeps only subpopulation and number of trips;
- head: MLP on [z, h_new, h_par, z*h_new, z*h_par, h_new - h_par, parent score].
Reference: -parent score. Metric: AUC overall and per innovation type (mode, time, route) and cohort."""
import argparse, json, time
import numpy as np
import torch
import torch.nn as nn

KINDS = ['mode', 'time', 'route']
D = 64


def auc(score, y):
    y = np.asarray(y, bool); n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0: return float('nan')
    r = np.empty(len(score)); order = np.argsort(score, kind='mergesort'); r[order] = np.arange(1, len(score) + 1)
    s = np.asarray(score)[order]; i = 0  # average ranks of ties
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[i]: j += 1
        if j > i: r[order[i:j + 1]] = (i + j + 2) / 2
        i = j + 1
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


class Net(nn.Module):
    def __init__(self, n_states, n_cells, adj, summ_dim, version):
        super().__init__()
        self.version = version
        self.cell = nn.Embedding(n_cells + 1, 16)          # +1: padding index n_cells
        self.hour = nn.Embedding(32, 16); self.mode = nn.Embedding(9, 16); self.act = nn.Embedding(7, 8)
        self.city_in = nn.Linear(3 + 16, 32); self.city_mp = nn.ModuleList([nn.Linear(64, 32) for _ in range(2)])
        self.city_const = nn.Parameter(torch.zeros(n_cells, 30, 32))
        A = torch.zeros(n_cells - 1, n_cells - 1)
        if len(adj): A[adj[:, 0], adj[:, 1]] = 1
        self.register_buffer('A', A / A.sum(1, keepdim=True).clamp(min=1))
        layer = lambda: nn.TransformerEncoder(nn.TransformerEncoderLayer(D, 4, 128, 0.1, batch_first=True), 2)
        self.plan_in = nn.Linear(16 * 4 + 8 * 2 + 1 + 64, D); self.plan_enc = layer()
        self.act_in = nn.Linear(8 + 16 + 16, D); self.act_enc = layer()
        self.agent_out = nn.Sequential(nn.Linear(D + summ_dim, D), nn.ReLU(), nn.Linear(D, D))
        self.agent_small = nn.Sequential(nn.Linear(4, D), nn.ReLU(), nn.Linear(D, D))
        self.head = nn.Sequential(nn.Linear(6 * D + 1, 128), nn.ReLU(), nn.Dropout(0.1), nn.Linear(128, 1))

    def city(self, X):
        """X [S, C-1, 30, 3] -> E [S, C, 30, 32] with a zero row for the 'other' cell."""
        if self.version == 'no_city':
            E = self.city_const.unsqueeze(0).expand(X.shape[0], -1, -1, -1)
            return torch.cat([E[:, :-1], torch.zeros_like(E[:, :1])], 1)
        h = self.hour.weight[:30].view(1, 1, 30, 16).expand(X.shape[0], X.shape[1], -1, -1)
        e = torch.relu(self.city_in(torch.cat([X, h], -1)))
        for mp in self.city_mp:
            nb = torch.einsum('ij,sjhd->sihd', self.A, e)
            e = e + torch.relu(mp(torch.cat([e, nb], -1)))
        return torch.cat([e, torch.zeros_like(e[:, :1])], 1)

    def plan(self, tok, dep, E, state):
        pad = tok[..., 0] < 0
        pad[:, 0] = False                                              # plans without trips: avoid an all-masked row
        t = tok.clamp(min=0).long()
        o, d, hr = t[..., 2], t[..., 3], t[..., 1]
        Eo = E[state[:, None], o, hr]; Ed = E[state[:, None], d, hr]
        x = torch.cat([self.mode(t[..., 0]), self.hour(hr), self.cell(o), self.cell(d),
                       self.act(t[..., 4]), self.act(t[..., 5]), dep.unsqueeze(-1) / 24, Eo, Ed], -1)
        x = self.plan_enc(self.plan_in(x), src_key_padding_mask=pad)
        m = (~pad).float().unsqueeze(-1)
        return (x * m).sum(1) / m.sum(1).clamp(min=1)

    def agent(self, act, summ):
        if self.version == 'no_agent':
            return self.agent_small(summ[:, :4])
        pad = act[..., 0] < 0
        pad[:, 0] = False
        t = act.clamp(min=0).long()
        x = self.act_enc(self.act_in(torch.cat([self.act(t[..., 0]), self.cell(t[..., 1]), self.hour(t[..., 2])], -1)),
                         src_key_padding_mask=pad)
        m = (~pad).float().unsqueeze(-1)
        return self.agent_out(torch.cat([(x * m).sum(1) / m.sum(1).clamp(min=1), summ], -1))

    def forward(self, X, b):
        E = self.city(X)
        hn = self.plan(b['new'], b['new_dep'], E, b['state']); hp = self.plan(b['par'], b['par_dep'], E, b['state'])
        z = self.agent(b['act'], b['summ'])
        return self.head(torch.cat([z, hn, hp, z * hn, z * hp, hn - hp, b['par_score'].unsqueeze(-1)], -1)).squeeze(-1)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('samples'); ap.add_argument('city'); ap.add_argument('--out', required=True)
    ap.add_argument('--versions', default='full,no_city,no_agent'); ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--epochs', type=int, default=20); ap.add_argument('--patience', type=int, default=3)
    a = ap.parse_args()
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    S = np.load(a.samples); C = np.load(a.city)
    n_cells = int(S['n_cells'])                                      # includes the 'other' cell
    X = torch.tensor(C['X'], device=dev)
    lx = X.clone(); lx[..., 0] = lx[..., 0] / 5; lx[..., 1] = lx[..., 1].clamp(max=5) - 1; X = lx
    seed, val = S['seed'], S['val'].astype(bool)
    tr, va, te = (seed == 4711) & ~val, (seed == 4711) & val, seed == 4712
    ps = S['par_score'].astype(np.float32); mu, sd = ps[tr].mean(), ps[tr].std() + 1e-6
    summ = S['summ'].astype(np.float32).copy()
    smu, ssd = summ[tr].mean(0), summ[tr].std(0) + 1e-6
    summ[:, 3:7] = (summ[:, 3:7] - smu[3:7]) / ssd[3:7]               # trips, plans, best, mean score
    arrays = {'new': S['new'], 'new_dep': S['new_dep'], 'par': S['par'], 'par_dep': S['par_dep'], 'act': S['act'],
              'summ': summ, 'par_score': (ps - mu) / sd, 'state': S['state']}
    y = (S['label'] > 0).astype(np.float32); kind = S['kind']; rel = S['related'].astype(bool)
    print(f'device {dev}; train {tr.sum()}, val {va.sum()}, test {te.sum()}; cells {n_cells}', flush=True)

    def batches(idx, bs, shuffle):
        if shuffle: idx = np.random.permutation(idx)
        for i in range(0, len(idx), bs):
            j = idx[i:i + bs]
            b = {k: torch.as_tensor(v[j], device=dev) for k, v in arrays.items()}
            b['new'] = b['new'].long(); b['par'] = b['par'].long(); b['act'] = b['act'].long(); b['state'] = b['state'].long()
            yield b, j

    def predict(model, idx):
        model.eval(); out = np.empty(len(idx), np.float32); pos = 0
        with torch.no_grad():
            for b, j in batches(idx, 4096, False):
                p = model(X, b).float().cpu().numpy(); out[pos:pos + len(j)] = p; pos += len(j)
        return out

    def report(score, idx):
        r = {'all': auc(score, y[idx])}
        for k, name in enumerate(KINDS):
            m = kind[idx] == k; r[name] = auc(score[m], y[idx][m])
            for coh, cm in (('related', rel[idx]), ('unrelated', ~rel[idx])):
                mm = m & cm; r[f'{name}_{coh}'] = auc(score[mm], y[idx][mm])
        return r

    te_idx = np.nonzero(te)[0]
    results = {'n': {'train': int(tr.sum()), 'val': int(va.sum()), 'test': int(te.sum())},
               'test_better_share': {name: float(y[te_idx][kind[te_idx] == k].mean()) for k, name in enumerate(KINDS)},
               'reference_parent_score': report(-arrays['par_score'][te_idx], te_idx), 'versions': {}}
    print('reference', json.dumps(results['reference_parent_score']), flush=True)
    adj = torch.tensor(C['adj'], dtype=torch.long)
    for version in a.versions.split(','):
        results['versions'][version] = []
        for run in range(a.runs):
            torch.manual_seed(run); np.random.seed(run)
            model = Net(len(C['states']), n_cells, adj, summ.shape[1], version).to(dev)
            opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
            lossf = nn.BCEWithLogitsLoss()
            best, best_state, bad, t0 = -1, None, 0, time.time()
            for ep in range(a.epochs):
                model.train()
                for b, j in batches(np.nonzero(tr)[0], 512, True):
                    loss = lossf(model(X, b), torch.as_tensor(y[j], device=dev))
                    opt.zero_grad(); loss.backward(); opt.step()
                v = auc(predict(model, np.nonzero(va)[0]), y[va])
                print(f'{version} run {run} epoch {ep}: val AUC {v:.4f} ({time.time() - t0:.0f}s)', flush=True)
                if v > best + 1e-4: best, bad, best_state = v, 0, {k: t.detach().clone() for k, t in model.state_dict().items()}
                else:
                    bad += 1
                    if bad >= a.patience: break
            model.load_state_dict(best_state)
            r = report(predict(model, te_idx), te_idx)
            r.update(val_auc=best, epochs=ep + 1, params=sum(p.numel() for p in model.parameters()))
            results['versions'][version].append(r)
            print(f'{version} run {run} test', json.dumps(r), flush=True)
            with open(a.out, 'w') as f: json.dump(results, f, indent=1)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
