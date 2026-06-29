"""
prevision_ca_services.py

Revenue projections adapted from prevision_ca_v2.py for web serving.
Uses the stats cache written by stats_services.py.

The cache's 'stats' section contains a monthly pivot table with the stock
breakdown by semester of treatment — used directly to initialise the projection.
"""
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime

from .stats_services import _load_cache

# ── Grille tarifaire ──────────────────────────────────────────────────────────

GRILLE_TARIFAIRE = [
    ('2000-01-01', 345.0),
    ('2024-01-01', 375.0),
    ('2026-01-01', 395.0),
]

PRIX_BILAN       = 130.0
PRIX_CS          = 23.0
PRIX_CONT1       = 400.0
DUREE_CONT_MOIS  = 18.0
DUREE_SURV_MOIS  = 24.0
RATIO_CSDV       = 0.54

DEFAULTS = {
    'bilans_sem':      None,   # None = calculé auto depuis rdvs
    'sem_trav':        42,
    'taux_conv':       None,   # None = calculé auto depuis rdvs
    'duree_ttt':       None,   # None = calculé auto depuis rdvs
    'taux_contention': None,   # None = calculé auto depuis user params, sinon 0.775
    'mois':            36,
}

# Valeurs de fallback si le calcul auto échoue ou que les données sont insuffisantes
FALLBACKS = {
    'bilans_sem': 4.21,
    'taux_conv':  0.845,
    'duree_ttt':  5.10,
}

GROUPES_POST_TTT = {'fin-traitement', 'hors-traitement', 'contention1', 'contention2', 'surveillance'}

CONT_ACTES = {
    'Contrôle contention', 'Fin de contention', 'Donner GO', 'Controle GO',
    'Pose fil de contention collé',
    'Dépose 2 cont', 'Depose 2 fils collés', 'Depose 1 fil collé',
    'Depose 0 fil collé', 'Dépose avec fil collé', 'Dépose sans fil collé',
    'Depose ABD', 'Depose Att Chir',
}

MOIS_FR = {
    'Janvier': 1, 'Février': 2, 'Mars': 3, 'Avril': 4, 'Mai': 5, 'Juin': 6,
    'Juillet': 7, 'Août': 8, 'Septembre': 9, 'Octobre': 10, 'Novembre': 11, 'Décembre': 12,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def _mlabel(d):
    return d.strftime('%Y-%m')


def _tarif_pour(d_entree):
    grille = sorted(GRILLE_TARIFAIRE, key=lambda x: x[0], reverse=True)
    for seuil_str, t in grille:
        if d_entree >= _parse_date(seuil_str):
            return t
    return GRILLE_TARIFAIRE[0][1]


def _parse_month_col(label: str) -> date | None:
    """Parse a French month label like 'Juin 2026' into a date."""
    parts = label.split()
    if len(parts) == 2 and parts[0] in MOIS_FR:
        try:
            return date(int(parts[1]), MOIS_FR[parts[0]], 1)
        except ValueError:
            pass
    return None


# ── Paramètres auto depuis rdvs ───────────────────────────────────────────────

def compute_params_auto(patients_data: dict, sem_trav: int) -> dict:
    """
    Calcule les paramètres de projection directement depuis les rdvs :
    - bilans_sem  : bilans des 12 derniers mois ÷ sem_trav
    - taux_conv   : taux de conversion bilan→traitement (méthode analyse)
    - duree_ttt   : durée moyenne de traitement en semestres (méthode analyse)
    """
    import statistics as _stats
    from datetime import date
    from .stats_services import (
        _compute_durees, _compute_conversion,
        BILAN_ACTES, JOURS_PAR_SEMESTRE,
    )

    result: dict[str, float | None] = {}

    # ── bilans/sem : compte les bilans des 12 derniers mois ──────────────────
    today         = date.today()
    one_year_ago  = date(today.year - 1, today.month, today.day)
    nb_bilans = 0
    for p in patients_data.values():
        for rdv in p.get('rdvs', []):
            if rdv.get('acte_type', '') in BILAN_ACTES:
                d = _parse_date(rdv.get('date', ''))
                if d and one_year_ago <= d <= today:
                    nb_bilans += 1
    result['bilans_sem'] = round(nb_bilans / sem_trav, 2) if sem_trav and nb_bilans else None

    # ── taux_conv et duree_ttt : réutilise les fonctions de stats_services ───
    try:
        converti, non_converti, _ = _compute_conversion(patients_data)
        total = len(converti) + len(non_converti)
        result['taux_conv'] = round(len(converti) / total, 3) if total >= 10 else None
    except Exception:
        result['taux_conv'] = None

    try:
        duree_results, _ = _compute_durees(patients_data)
        durees = [r['duree_semestres'] for r in duree_results]
        result['duree_ttt'] = round(_stats.mean(durees), 2) if len(durees) >= 10 else None
    except Exception:
        result['duree_ttt'] = None

    return result


# ── Taux de contention ────────────────────────────────────────────────────────

def compute_taux_contention(patients_data: dict) -> tuple[float, int | None, int | None, str]:
    """
    Fraction des patients post-traitement avec au moins un acte de contention.
    Si user_statistics_group disponible : méthode exacte par groupe.
    Sinon : retourne la valeur mesurée (0.775).
    """
    has_groups = any(p.get('user_statistics_group') for p in patients_data.values())
    if not has_groups:
        return 0.775, None, None, 'défaut mesuré'

    nb_total = nb_avec = 0
    for p in patients_data.values():
        if p.get('user_statistics_group', '') not in GROUPES_POST_TTT:
            continue
        nb_total += 1
        if {r.get('acte_type', '') for r in p.get('rdvs', [])} & CONT_ACTES:
            nb_avec += 1
    taux = nb_avec / nb_total if nb_total > 0 else 0.775
    return taux, nb_avec, nb_total, 'groupe'


# ── Stock depuis la section stats ─────────────────────────────────────────────

def _stock_from_stats(stats: list[dict]) -> tuple[dict, int, int, int, str]:
    """
    Initialise le stock de patients depuis la table pivot mensuelle.

    La section stats a des lignes 'Semestre 1'…'Semestre 7', 'Au delà',
    'Contention 1', 'Contention 2', 'Surveillance'.

    Chaque semestre de traitement correspond à une cohorte d'entrée :
      Semestre N (en Juin 2026) → entrée ~(N-0.5)×6 mois avant → tarif déduit.

    Retourne (stock_by_tarif, nb_c1, nb_c2, nb_sv, month_label).
    """
    today = date.today()

    all_cols = [k for k in stats[0].keys() if k != 'Unnamed: 0']
    current_col = max(
        (c for c in all_cols if _parse_month_col(c) and _parse_month_col(c) <= today),
        key=lambda c: _parse_month_col(c),
        default=all_cols[-1],
    )

    row = {r.get('Unnamed: 0', ''): int(r.get(current_col) or 0) for r in stats}

    stock: dict[float, float] = defaultdict(float)
    for n in range(1, 8):
        cnt = row.get(f'Semestre {n}', 0)
        if cnt <= 0:
            continue
        months_in = (n - 0.5) * 6
        est_entree = _add_months(today, -round(months_in))
        stock[_tarif_pour(est_entree)] += cnt

    cnt_au_dela = row.get('Au delà', 0)
    if cnt_au_dela > 0:
        est_entree = _add_months(today, -round(7.5 * 6))
        stock[_tarif_pour(est_entree)] += cnt_au_dela

    nb_c1 = row.get('Contention 1', 0)
    nb_c2 = row.get('Contention 2', 0)
    nb_sv = row.get('Surveillance', 0)

    return dict(stock), nb_c1, nb_c2, nb_sv, current_col


# ── Echeances réelles ─────────────────────────────────────────────────────────

def _load_echeances_by_month(ech_data: list) -> dict:
    today_m = date.today().strftime('%Y-%m')
    by_m: dict = defaultdict(lambda: defaultdict(float))
    for e in ech_data:
        m = e.get('Date', '')[:7]
        if m < today_m:
            continue
        acte = e.get('Acte', '').lower()
        du   = e.get('Du', e.get('Dû', 0)) or 0
        if '1/2 semestre' in acte or 'trimestre' in acte:
            cat = 'forfait'
        elif 'contention 1' in acte:
            cat = 'cont1'
        elif 'contention 2' in acte:
            cat = 'cont2'
        elif 'surveillance' in acte:
            cat = 'surv'
        elif 'bilan' in acte:
            cat = 'bilan'
        elif 'consultation' in acte:
            cat = 'cs'
        else:
            cat = 'autre'
        by_m[m][cat] += du
    return dict(by_m)


# ── Projection mensuelle ──────────────────────────────────────────────────────

def _run_projection(
    stock_by_tarif: dict[float, float],
    nb_c1: int, nb_c2: int, nb_sv: int,
    ech_by_m: dict,
    cfg: dict,
) -> list[dict]:
    today       = date.today()
    bilans_mois = cfg['bilans_sem'] * cfg['sem_trav'] / 12
    cs1_mois    = bilans_mois
    csdv_mois   = cs1_mois * RATIO_CSDV
    duree_mois  = cfg['duree_ttt'] * 6
    taux_conv   = cfg['taux_conv']
    taux_cont   = cfg['taux_contention']

    s     = defaultdict(float, stock_by_tarif)
    cont1 = float(nb_c1)
    cont2 = float(nb_c2)
    surv  = float(nb_sv)

    tarif_actuel = _tarif_pour(today)

    rows = []
    for i in range(cfg['mois']):
        mois_date = _add_months(today.replace(day=1), i)
        mois_str  = _mlabel(mois_date)

        for seuil_str, t in sorted(GRILLE_TARIFAIRE, key=lambda x: x[0]):
            if _parse_date(seuil_str) and mois_date >= _parse_date(seuil_str):
                tarif_actuel = t

        ca_forfait = sum(v * t * 2 / 6 for t, v in s.items())
        sortants   = sum(v / duree_mois for v in s.values())
        ca_cont    = sortants * PRIX_CONT1 * taux_cont
        ca_bilans  = bilans_mois * PRIX_BILAN
        ca_cs      = (cs1_mois + csdv_mois) * PRIX_CS
        ca_total   = ca_forfait + ca_cont + ca_bilans + ca_cs

        ech    = ech_by_m.get(mois_str, {})
        ca_ech = sum(ech.values()) if ech else None

        rows.append({
            'mois':               mois_str,
            'stock_ttt':          round(sum(s.values())),
            'stock_cont':         round(cont1 + cont2),
            'stock_surv':         round(surv),
            'nb_bilans_mois':     round(bilans_mois, 1),
            'ca_forfait':         round(ca_forfait),
            'ca_contention':      round(ca_cont),
            'ca_bilans_actes':    round(ca_bilans),
            'ca_cs_actes':        round(ca_cs),
            'ca_total_projete':   round(ca_total),
            'ca_total_echeances': round(ca_ech) if ca_ech is not None else None,
            'stock_345':          round(s.get(345.0, 0)),
            'stock_375':          round(s.get(375.0, 0)),
            'stock_395':          round(s.get(395.0, 0)),
        })

        for t in list(s.keys()):
            s[t] = max(0.0, s[t] - s[t] / duree_mois)
        s[tarif_actuel] = s.get(tarif_actuel, 0.0) + bilans_mois * taux_conv

        sortants_cont = (cont1 + cont2) / DUREE_CONT_MOIS
        cont1 = max(0.0, cont1 - cont1 / DUREE_CONT_MOIS + sortants)
        cont2 = max(0.0, cont2 - cont2 / DUREE_CONT_MOIS)
        surv  = max(0.0, surv  - surv  / DUREE_SURV_MOIS  + sortants_cont)

    return rows


def _build_annual_summary(rows: list[dict]) -> list[dict]:
    by_y: dict = defaultdict(lambda: defaultdict(float))
    for r in rows:
        y = r['mois'][:4]
        by_y[y]['nb_mois'] += 1
        for k in ['ca_forfait', 'ca_contention', 'ca_bilans_actes', 'ca_cs_actes', 'ca_total_projete']:
            by_y[y][k] += r.get(k, 0) or 0
        by_y[y]['stock_fin'] = r['stock_ttt']

    result = []
    for y in sorted(by_y):
        d = by_y[y]
        nm = max(d['nb_mois'], 1)
        result.append({
            'annee':            y,
            'stock_fin_annee':  round(d['stock_fin']),
            'ca_forfait':       round(d['ca_forfait']),
            'ca_contention':    round(d['ca_contention']),
            'ca_bilans_actes':  round(d['ca_bilans_actes']),
            'ca_cs_actes':      round(d['ca_cs_actes']),
            'ca_total_annuel':  round(d['ca_total_projete']),
            'ca_moyen_mensuel': round(d['ca_total_projete'] / nm),
        })
    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_prevision_data(cfg: dict | None = None) -> dict:
    """
    Run projection from cache and return JSON-serialisable data.
    cfg overrides any DEFAULTS keys.
    """
    params = dict(DEFAULTS)
    if cfg:
        for k, v in cfg.items():
            if k in params and v is not None:
                params[k] = v

    cache     = _load_cache()
    stats     = cache.get('stats', [])
    echeances = cache.get('echeances', [])
    patients  = cache.get('users_rdvs', {})

    # ── Paramètres auto ───────────────────────────────────────────────────────
    auto = compute_params_auto(patients, params['sem_trav'])
    params_sources: dict[str, str] = {}

    for key in ('bilans_sem', 'taux_conv', 'duree_ttt'):
        if params[key] is None:
            measured = auto.get(key)
            if measured is not None:
                params[key]        = measured
                params_sources[key] = 'mesuré'
            else:
                params[key]        = FALLBACKS[key]
                params_sources[key] = 'défaut'
        else:
            params_sources[key] = 'manuel'

    # Taux de contention : calculé depuis les user params si disponibles
    taux_cont_methode   = 'manuel'
    taux_cont_nb_avec   = None
    taux_cont_nb_total  = None
    if params['taux_contention'] is None:
        taux, nb_avec, nb_total, methode = compute_taux_contention(patients)
        params['taux_contention'] = taux
        taux_cont_methode  = methode
        taux_cont_nb_avec  = nb_avec
        taux_cont_nb_total = nb_total
        params_sources['taux_contention'] = methode
    else:
        params_sources['taux_contention'] = 'manuel'

    stock_by_tarif, nb_c1, nb_c2, nb_sv, stock_month = _stock_from_stats(stats)
    nb_ttt = round(sum(stock_by_tarif.values()))

    ech_by_m = _load_echeances_by_month(echeances)
    rows     = _run_projection(stock_by_tarif, nb_c1, nb_c2, nb_sv, ech_by_m, params)
    summary  = _build_annual_summary(rows)

    jalons = []
    for cible in [50_000, 55_000, 60_000]:
        idx = next((i for i, r in enumerate(rows) if r['ca_total_projete'] >= cible), None)
        jalons.append({
            'cible':    cible,
            'atteint':  idx is not None,
            'mois_idx': idx,
            'mois':     rows[idx]['mois'] if idx is not None else None,
        })

    return {
        'params':         params,
        'params_sources': params_sources,
        'params_mesures': auto,
        'stock_info': {
            'nb_ttt':              nb_ttt,
            'nb_cont1':            nb_c1,
            'nb_cont2':            nb_c2,
            'nb_surv':             nb_sv,
            'stock_month':         stock_month,
            'stock_by_tarif':      {str(int(t)): round(v) for t, v in stock_by_tarif.items()},
            'taux_cont':           round(params['taux_contention'], 4),
            'taux_cont_methode':   taux_cont_methode,
            'taux_cont_nb_avec':   taux_cont_nb_avec,
            'taux_cont_nb_total':  taux_cont_nb_total,
        },
        'mensuel':  rows,
        'annuel':   summary,
        'jalons':   jalons,
        'defaults': DEFAULTS,
    }
