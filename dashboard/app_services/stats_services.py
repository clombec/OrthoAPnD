"""
stats_services.py

Ortho statistics computed from the anonymised patients cache
(same data as analyse_ortho.py, adapted for web serving).

Cache file: <project_root>/downloads/stats_cache.json
Format   : {"users_rdvs": {...}, "echeances": [...], "timestamp": "ISO"}
"""
import csv
import io
import json
import statistics
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from orthoaget.session import OrthoASession

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "stats_cache.json"

# ── Nomenclature (mirrors analyse_ortho.py) ───────────────────────────────────

BILAN_ACTES  = {'Bilan', 'Bilan court', 'BilanR'}
CS1_ACTES    = {'1ere CS '}
CSDV_ACTES   = {'CS Déjà Vu', 'CS Adulte'}
CS_ACTES     = CS1_ACTES | CSDV_ACTES

DTT_ACTES = {
    'DTT Pose Disjoncteur', 'DTT Collage MB H ind', 'DTT Pose CM',
    'DTT Pose MB H CD', 'DTT Pose Disjoncteur + Arc lingual',
    'DTT Pose Arc Lingual', 'DTT Pose ATP', 'DTT Pose ATP + AL',
    'DTT Pose Bibagues et MB Ind', 'DTT Pose Bibagues + MB H Ind',
    'DTT Collage MB B Ind', 'DTT MB H et B indirect',
    'DTT Pose MB B CD', 'DTT Pose MB H et B Direct',
    'DTT Pose Educateur Fonctionnel', 'DTT Aligneurs', 'Début TT Pose H/B',
}

DEPOSE_ACTES = {
    'Dépose 2 cont', 'Depose 2 fils collés', 'Depose 1 fil collé',
    'Depose 0 fil collé', 'Dépose avec fil collé', 'Dépose sans fil collé',
    'Depose ABD', 'Depose Att Chir',
}

GROUPES_VALIDES_DUREE = {'fin-traitement', 'hors-traitement', 'contention1', 'contention2'}
GROUPES_EXCLUS_DUREE  = {'sans-traitement', 'aed', 'traitement'}

DEBUT_CONVERSION   = date(2022, 1, 1)
JOURS_MIN_RECUL    = 365
JOURS_PAR_SEMESTRE = 365.25 / 2

# ── Cache helpers ─────────────────────────────────────────────────────────────

def is_cache_available() -> bool:
    return CACHE_PATH.exists()


def get_cache_timestamp() -> str | None:
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH, encoding='utf-8') as f:
            data = json.load(f)
        return data.get('timestamp')
    except Exception:
        return None


def _load_cache() -> dict:
    with open(CACHE_PATH, encoding='utf-8') as f:
        return json.load(f)


def _load_patients() -> dict:
    data = _load_cache()
    return data.get('users_rdvs', data)


def _load_echeances() -> list:
    data = _load_cache()
    return data.get('echeances', [])


# ── External refresh ──────────────────────────────────────────────────────────

def refresh_from_external(progress_cb=None) -> None:
    def _p(text: str, pct: int) -> None:
        if progress_cb:
            progress_cb(text, pct)

    _p("Connexion à OrthoAdvance…", 5)
    with OrthoASession(get_all_user_data=True) as session:
        _p("Téléchargement des données patients…", 20)
        all_stats = session.get_anonymized_data()

    _p("Enregistrement du cache…", 90)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=4)
    _p("Chargement terminé", 100)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s: str):
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


def _quarter_label(d: date) -> str:
    return f'T{(d.month - 1) // 3 + 1} {d.year}'


def _quarter_sort_key(label: str) -> int:
    t, y = label.split()
    return int(y) * 10 + int(t[1])


# ── 1. Durée de traitement ────────────────────────────────────────────────────

def _compute_durees(patients: dict) -> tuple[list[dict], Counter]:
    skipped = Counter()
    results = []

    for pid, p in patients.items():
        group   = p.get('user_statistics_group', '')

        rdvs = sorted(
            [r for r in p.get('rdvs', []) if _parse_date(r.get('date', ''))],
            key=lambda r: r['date'],
        )
        if len(rdvs) <= 2:
            skipped['trop peu de rdvs'] += 1
            continue

        bilan_rdvs = [r for r in rdvs if r.get('acte_type', '') in BILAN_ACTES]
        if not bilan_rdvs:
            skipped['pas de bilan'] += 1
            continue
        last_bilan = _parse_date(bilan_rdvs[-1]['date'])

        rdvs_apres = [r for r in rdvs if _parse_date(r['date']) > last_bilan]
        depose = next(
            (r for r in rdvs_apres if r.get('acte_type', '') in DEPOSE_ACTES), None
        )
        if not depose:
            skipped['pas de dépose explicite'] += 1
            continue

        date_fin = _parse_date(depose['date'])
        if date_fin <= last_bilan:
            skipped['date_fin <= date_bilan'] += 1
            continue

        duree = round((date_fin - last_bilan).days / JOURS_PAR_SEMESTRE, 2)
        if duree < 1.0:
            skipped['durée < 1 semestre'] += 1
            continue

        results.append({
            'id_patient':          pid,
            'groupe':              group,
            'type_cs':             p.get('type_cs') or '',
            'date_dernier_bilan':  str(last_bilan),
            'date_fin_traitement': str(date_fin),
            'duree_semestres':     duree,
            'acte_depose':         depose['acte_type'],
        })

    return results, skipped


def _stats_duree(results: list[dict], skipped: Counter) -> dict:
    durees = [r['duree_semestres'] for r in results]
    n = len(durees)
    if n < 2:
        exclus = [{'raison': k, 'count': v} for k, v in skipped.most_common()]
        return {'n': n, 'error': 'Données insuffisantes (moins de 2 patients éligibles)', 'exclus': exclus}

    distribution = []
    for lo, hi, label in [(1, 3, '1–3 sem'), (3, 5, '3–5 sem'), (5, 7, '5–7 sem'),
                           (7, 9, '7–9 sem'), (9, 99, '9+ sem')]:
        cnt = sum(1 for d in durees if lo <= d < hi)
        distribution.append({'label': label, 'count': cnt, 'pct': round(cnt / n * 100, 1)})

    par_groupe = []
    for g in sorted(set(r['groupe'] for r in results)):
        sub = [r['duree_semestres'] for r in results if r['groupe'] == g]
        par_groupe.append({
            'groupe': g, 'n': len(sub),
            'moy': round(statistics.mean(sub), 2),
            'med': round(statistics.median(sub), 2),
            'sigma': round(statistics.stdev(sub) if len(sub) > 1 else 0.0, 2),
        })

    par_depose = []
    for acte, cnt in Counter(r['acte_depose'] for r in results).most_common():
        sub = [r['duree_semestres'] for r in results if r['acte_depose'] == acte]
        par_depose.append({'acte': acte, 'count': cnt, 'moy': round(statistics.mean(sub), 2)})

    exclus = [{'raison': k, 'count': v} for k, v in skipped.most_common()]

    return {
        'n':            n,
        'moy':          round(statistics.mean(durees), 3),
        'med':          round(statistics.median(durees), 3),
        'sigma':        round(statistics.stdev(durees), 3),
        'variance':     round(statistics.variance(durees), 3),
        'min':          round(min(durees), 2),
        'max':          round(max(durees), 2),
        'q1':           round(statistics.quantiles(durees, n=4)[0], 3),
        'q3':           round(statistics.quantiles(durees, n=4)[2], 3),
        'distribution': distribution,
        'par_groupe':   par_groupe,
        'par_depose':   par_depose,
        'exclus':       exclus,
    }


# ── 2. Taux de conversion ─────────────────────────────────────────────────────

def _compute_conversion(patients: dict) -> tuple[list[dict], list[dict], list[dict]]:
    today     = date.today()
    cutoff_1y = today - timedelta(days=JOURS_MIN_RECUL)
    converti, non_converti, exclu = [], [], []

    for pid, p in patients.items():
        rdvs = sorted(
            [r for r in p.get('rdvs', []) if _parse_date(r.get('date', ''))],
            key=lambda r: r['date'],
        )
        bilan_rdvs = [r for r in rdvs if r.get('acte_type', '') in BILAN_ACTES]
        if not bilan_rdvs:
            continue
        bilan_date = _parse_date(bilan_rdvs[-1]['date'])

        if bilan_date < DEBUT_CONVERSION:
            exclu.append({'id_patient': pid, 'date_bilan': str(bilan_date),
                          'statut': 'exclu', 'raison': 'avant 2022',
                          'groupe': p.get('user_statistics_group', ''),
                          'nb_rdvs_apres': 0, 'has_dtt': False, 'type_cs': p.get('type_cs') or ''})
            continue

        rdvs_after_non_cs = [
            r for r in rdvs
            if _parse_date(r['date']) > bilan_date and r.get('acte_type', '') not in CS_ACTES
        ]
        has_dtt  = any(r.get('acte_type', '') in DTT_ACTES for r in rdvs_after_non_cs)
        nb_after = len(rdvs_after_non_cs)
        is_conv  = has_dtt or nb_after >= 2

        row = {
            'id_patient':    pid,
            'groupe':        p.get('user_statistics_group', ''),
            'type_cs':       p.get('type_cs') or '',
            'date_bilan':    str(bilan_date),
            'has_dtt':       has_dtt,
            'nb_rdvs_apres': nb_after,
        }

        if is_conv:
            row['statut'] = 'converti'
            row['raison'] = 'DTT' if has_dtt else f'{nb_after} rdvs non-CS'
            converti.append(row)
        elif bilan_date > cutoff_1y:
            row['statut'] = 'exclu'
            row['raison'] = f'bilan < 1 an ({(today - bilan_date).days}j)'
            exclu.append(row)
        else:
            row['statut'] = 'non converti'
            row['raison'] = f'{nb_after} rdvs non-CS après bilan'
            non_converti.append(row)

    return converti, non_converti, exclu


def _stats_conversion(converti, non_converti, exclu) -> dict:
    total = len(converti) + len(non_converti)
    taux  = len(converti) / total * 100 if total else 0

    excl_reasons = Counter(r['raison'].split('(')[0].strip() for r in exclu)

    by_q = defaultdict(lambda: {'c': 0, 'nc': 0, 'excl': 0})
    for r in converti:
        by_q[_quarter_label(_parse_date(r['date_bilan']))]['c'] += 1
    for r in non_converti:
        by_q[_quarter_label(_parse_date(r['date_bilan']))]['nc'] += 1
    for r in exclu:
        d = _parse_date(r['date_bilan'])
        if d >= DEBUT_CONVERSION:
            by_q[_quarter_label(d)]['excl'] += 1

    par_trimestre = []
    for q in sorted(by_q, key=_quarter_sort_key):
        d   = by_q[q]
        tot = d['c'] + d['nc']
        tx  = d['c'] / tot * 100 if tot else 0.0
        par_trimestre.append({
            'trimestre': q, 'eligible': tot,
            'converti': d['c'], 'non_converti': d['nc'],
            'taux': round(tx, 1), 'exclus': d['excl'],
        })

    nc_groups = Counter(r['groupe'] for r in non_converti)

    return {
        'total_eligible':  total,
        'nb_converti':     len(converti),
        'nb_non_converti': len(non_converti),
        'nb_exclu':        len(exclu),
        'taux':            round(taux, 1),
        'debut_periode':   str(DEBUT_CONVERSION),
        'jours_recul':     JOURS_MIN_RECUL,
        'excl_raisons':    [{'raison': k, 'count': v} for k, v in excl_reasons.most_common()],
        'par_trimestre':   par_trimestre,
        'nc_groupes':      [{'groupe': k, 'count': v} for k, v in nc_groups.most_common()],
    }


# ── 3. Funnel CS → Bilan → Traitement ────────────────────────────────────────

def _compute_funnel(patients: dict, taux_conv_bilan_ttt: float) -> dict:
    today     = date.today()
    cutoff_1y = today - timedelta(days=JOURS_MIN_RECUL)
    chemins   = []

    DEPOSE_LOCAL = DEPOSE_ACTES

    for pid, p in patients.items():
        rdvs = sorted(
            [r for r in p.get('rdvs', []) if _parse_date(r.get('date', ''))],
            key=lambda r: r['date'],
        )
        bilans_elig = [r for r in rdvs
                       if r.get('acte_type', '') in BILAN_ACTES
                       and _parse_date(r['date']) >= DEBUT_CONVERSION]
        if not bilans_elig:
            continue
        bilan_date = _parse_date(bilans_elig[0]['date'])

        rdvs_avant = [r for r in rdvs if _parse_date(r['date']) < bilan_date]
        fin_cycle_prec = None
        for r in reversed(rdvs_avant):
            if r.get('acte_type', '') in DEPOSE_LOCAL or r.get('acte_type', '') in DTT_ACTES:
                fin_cycle_prec = _parse_date(r['date'])
                break

        cs_cycle = [r for r in rdvs_avant
                    if r.get('acte_type', '') in CS_ACTES
                    and (fin_cycle_prec is None or _parse_date(r['date']) > fin_cycle_prec)]

        n_cs1  = sum(1 for r in cs_cycle if r.get('acte_type', '') in CS1_ACTES)
        n_csdv = sum(1 for r in cs_cycle if r.get('acte_type', '') in CSDV_ACTES)

        seq = ['CS1' if r.get('acte_type', '') in CS1_ACTES else 'DV' for r in cs_cycle]

        delai_derniere_cs = delai_cs1_bilan = None
        if cs_cycle:
            delai_derniere_cs = (bilan_date - _parse_date(cs_cycle[-1]['date'])).days
        cs1_dates = [_parse_date(r['date']) for r in cs_cycle if r.get('acte_type', '') in CS1_ACTES]
        if cs1_dates:
            delai_cs1_bilan = (bilan_date - min(cs1_dates)).days

        DELAI_MAX   = 365
        delai_exclu = delai_derniere_cs is not None and delai_derniere_cs > DELAI_MAX

        chemins.append({
            'id_patient':                    pid,
            'bilan_date':                    str(bilan_date),
            'n_cs1':                         n_cs1,
            'n_csdv':                        n_csdv,
            'n_cs_total':                    n_cs1 + n_csdv,
            'sequence':                      ' → '.join(seq) if seq else 'direct',
            'delai_derniere_cs_bilan_jours': delai_derniere_cs,
            'delai_cs1_bilan_jours':         delai_cs1_bilan,
            'delai_exclu':                   delai_exclu,
        })

    n = len(chemins)
    if n == 0:
        return {'error': 'Aucune donnée funnel'}, []

    via_cs1 = [c for c in chemins if c['n_cs1'] > 0]
    via_dv  = [c for c in chemins if c['n_cs1'] == 0 and c['n_csdv'] > 0]
    directs = [c for c in chemins if c['n_cs1'] == 0 and c['n_csdv'] == 0]

    # Taux CS1 → bilan
    cs1_eligs = cs1_bilan = 0
    for pid, p in patients.items():
        rdvs = sorted(
            [r for r in p.get('rdvs', []) if _parse_date(r.get('date', ''))],
            key=lambda r: r['date'],
        )
        cs1_rdvs = [r for r in rdvs if r.get('acte_type', '') in CS1_ACTES]
        if not cs1_rdvs:
            continue
        first_cs1 = _parse_date(cs1_rdvs[0]['date'])
        if first_cs1 < DEBUT_CONVERSION or first_cs1 > cutoff_1y:
            continue
        cs1_eligs += 1
        bilans_apres = [r for r in rdvs
                        if r.get('acte_type', '') in BILAN_ACTES
                        and _parse_date(r['date']) > first_cs1]
        if bilans_apres:
            cs1_bilan += 1

    taux_cs1_bilan = cs1_bilan / cs1_eligs if cs1_eligs else 0

    moy_csdv_via_cs1 = statistics.mean(c['n_csdv'] for c in via_cs1) if via_cs1 else 0
    pct_avec_csdv    = sum(1 for c in via_cs1 if c['n_csdv'] > 0) / len(via_cs1) if via_cs1 else 0
    moy_csdv_si_csdv = (statistics.mean(c['n_csdv'] for c in via_cs1 if c['n_csdv'] > 0)
                        if any(c['n_csdv'] > 0 for c in via_cs1) else 0)

    delais_dcs = [c['delai_derniere_cs_bilan_jours'] for c in via_cs1
                  if c['delai_derniere_cs_bilan_jours'] is not None and not c['delai_exclu']]
    delais_cs1 = [c['delai_cs1_bilan_jours'] for c in via_cs1
                  if c['delai_cs1_bilan_jours'] is not None and not c['delai_exclu']]
    nb_delai_exclu = sum(1 for c in via_cs1 if c['delai_exclu'])

    delai_dcs_moy = statistics.mean(delais_dcs)  if delais_dcs else 0
    delai_dcs_med = statistics.median(delais_dcs) if delais_dcs else 0
    delai_cs1_moy = statistics.mean(delais_cs1)   if delais_cs1 else 0
    delai_cs1_med = statistics.median(delais_cs1) if delais_cs1 else 0

    # Table de pilotage
    taux_ttt  = taux_conv_bilan_ttt
    pct_cs1   = len(via_cs1) / n
    table = []
    for b in [2.0, 2.5, 3.0, 3.5, 4.0, 4.21, 4.5, 5.0]:
        cas  = b * taux_ttt
        cs1  = (b * pct_cs1) / taux_cs1_bilan if taux_cs1_bilan > 0 else 0
        csdv = cs1 * moy_csdv_via_cs1
        table.append({
            'bilans':     b,
            'cas_ttt':    round(cas, 2),
            'cs1':        round(cs1, 2),
            'csdv':       round(csdv, 2),
            'total_cs':   round(cs1 + csdv, 2),
            'is_cible':   abs(b - 4.21) < 0.01,
        })

    return {
        'nb_bilans':           n,
        'nb_via_cs1':          len(via_cs1),
        'nb_via_dv':           len(via_dv),
        'nb_directs':          len(directs),
        'pct_via_cs1':         round(len(via_cs1) / n * 100, 1),
        'pct_via_dv':          round(len(via_dv)  / n * 100, 1),
        'pct_directs':         round(len(directs) / n * 100, 1),
        'cs1_eligs':           cs1_eligs,
        'cs1_avec_bilan':      cs1_bilan,
        'taux_cs1_bilan':      round(taux_cs1_bilan * 100, 1),
        'moy_csdv_via_cs1':    round(moy_csdv_via_cs1, 3),
        'pct_avec_csdv':       round(pct_avec_csdv * 100, 1),
        'moy_csdv_si_csdv':    round(moy_csdv_si_csdv, 2),
        'delai_dcs_moy_j':     round(delai_dcs_moy, 0),
        'delai_dcs_moy_sem':   round(delai_dcs_moy / 7, 1),
        'delai_dcs_med_j':     round(delai_dcs_med, 0),
        'delai_dcs_med_sem':   round(delai_dcs_med / 7, 1),
        'delai_cs1_moy_j':     round(delai_cs1_moy, 0),
        'delai_cs1_med_j':     round(delai_cs1_med, 0),
        'nb_delai_exclu':      nb_delai_exclu,
        'taux_conv_bilan_ttt': round(taux_conv_bilan_ttt * 100, 1),
        'table_pilotage':      table,
    }, chemins


# ── Main compute entry point ──────────────────────────────────────────────────

def compute_analyse_data() -> dict:
    """Run all 3 analyses and return JSON-serialisable data."""
    patients = _load_patients()

    results_duree, skipped = _compute_durees(patients)
    converti, non_converti, exclu = _compute_conversion(patients)

    taux_conv = len(converti) / max(len(converti) + len(non_converti), 1)
    stats_funnel, chemins = _compute_funnel(patients, taux_conv)

    return {
        'timestamp':  get_cache_timestamp(),
        'duree':      _stats_duree(results_duree, skipped),
        'conversion': _stats_conversion(converti, non_converti, exclu),
        'funnel':     stats_funnel,
        '_raw': {
            'duree':   results_duree,
            'conv_all': converti + non_converti + exclu,
            'chemins': chemins,
        },
    }


# ── CSV generators (on demand) ────────────────────────────────────────────────

def generate_csv_duree() -> str:
    patients = _load_patients()
    results, _ = _compute_durees(patients)
    fields = ['id_patient', 'groupe', 'type_cs',
              'date_dernier_bilan', 'date_fin_traitement',
              'duree_semestres', 'acte_depose']
    rows = sorted(results, key=lambda r: int(r['id_patient']))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, delimiter=';')
    w.writeheader()
    for row in rows:
        out = dict(row)
        out['duree_semestres'] = str(row['duree_semestres']).replace('.', ',')
        w.writerow(out)
    return buf.getvalue()


def generate_csv_conversion() -> str:
    patients = _load_patients()
    converti, non_converti, exclu = _compute_conversion(patients)
    all_rows = converti + non_converti + exclu
    fields   = ['id_patient', 'groupe', 'type_cs', 'date_bilan',
                'statut', 'raison', 'has_dtt', 'nb_rdvs_apres']
    rows = sorted(all_rows, key=lambda r: int(r['id_patient']))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def generate_csv_funnel() -> str:
    patients = _load_patients()
    converti, non_converti, _ = _compute_conversion(patients)
    taux_conv = len(converti) / max(len(converti) + len(non_converti), 1)
    _, chemins = _compute_funnel(patients, taux_conv)
    fields = ['id_patient', 'bilan_date', 'n_cs1', 'n_csdv', 'n_cs_total',
              'sequence', 'delai_derniere_cs_bilan_jours',
              'delai_cs1_bilan_jours', 'delai_exclu']
    rows = sorted(chemins, key=lambda r: int(r['id_patient']))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, delimiter=';', extrasaction='ignore')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
