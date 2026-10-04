"""Explicit whitelist boundary. Policies receive fresh JSON-compatible objects."""

def observe(history, agent, population=24, information='time', window=5):
    if information not in ('time', 'flow'):
        raise ValueError('Unknown observation condition')
    records = []
    for row in history[-window:]:
        record = {'day': row['day'], 'route': row['actions'][agent],
                  'travel_time': round(row['costs'][row['actions'][agent]], 6)}
        if information == 'flow':
            record['total_route_flows'] = list(row['total_flow'])
        records.append(record)
    return {'population': population, 'information': information, 'history': records}
