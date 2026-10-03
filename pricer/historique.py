"""Historique des courbes (CSV ;) et lignes publiees."""
import csv, datetime as dt
from .courbe import Courbe, Ligne


def charger_historique(chemin) -> dict:
    out = {}
    with open(chemin, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            try:
                d = dt.date.fromisoformat(r["date"])
                out[d] = [float(r[k]) for k in ("13s", "26s", "52s", "2a", "5a", "10a", "15a", "20a", "30a")]
            except Exception:
                continue
    return out


def charger_lignes(chemin) -> dict:
    out = {}
    with open(chemin, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            try:
                d = dt.date.fromisoformat(r["date_courbe"]); e = dt.date.fromisoformat(r["echeance"])
                out.setdefault(d, []).append(Ligne(e, float(r["taux"]), str(r.get("code") or ""), r.get("libelle") or ""))
            except Exception:
                continue
    for d in out:
        out[d].sort(key=lambda l: l.echeance)
    return out


def courbe_historique(hist: dict, lignes: dict, d: dt.date):
    """Courbe publiee a la date d, sinon la derniere publiee avant d (veille rapportee)."""
    dates = sorted(x for x in hist if x <= d)
    if not dates:
        return None
    base = dates[-1]
    return Courbe(base, hist[base], lignes.get(base, []), "publiee BKAM" if base == d else f"veille rapportee (courbe du {base:%d/%m/%Y})")


def ajouter(chemin, courbe: Courbe):
    rows = []
    try:
        with open(chemin, encoding="utf-8") as f:
            rows = [r for r in csv.reader(f, delimiter=";")]
    except FileNotFoundError:
        rows = [["date", "13s", "26s", "52s", "2a", "5a", "10a", "15a", "20a", "30a"]]
    rows = [r for r in rows if not r or r[0] != courbe.date.isoformat()]
    rows.append([courbe.date.isoformat()] + [f"{t:.6f}" for t in courbe.taux])
    with open(chemin, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerows(rows)
