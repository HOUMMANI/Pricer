"""Courbe du jour : courbe BKAM de base + cotations eBond, selon une regle de combinaison."""
from __future__ import annotations
import datetime as dt
from .courbe import Courbe, Ligne, tenors_depuis_points

REGLES = {
    "bkam": "BKAM seule : les cotations eBond sont ignorees",
    "lignes": "Lignes eBond : le mid remplace le taux des lignes cotees, les tenors sont recalcules sur l ensemble des points",
    "decalage": "Decalage : les tenors BKAM sont deplaces de la variation moyenne impliquee par les cotations eBond",
}


def courbe_du_jour(base: Courbe, cotations: list, ref: dict, d: dt.date, regle: str = "lignes") -> Courbe:
    """cotations : liste de dict(code, bid, ask) en taux decimal (bid > ask en taux). Retourne une nouvelle Courbe datee d."""
    if regle == "bkam" or not cotations:
        return Courbe(d, list(base.taux), list(base.lignes), base.source)
    mids = {}
    for q in cotations:
        try:
            bid, ask = float(q.get("bid") or 0), float(q.get("ask") or 0)
        except ValueError:
            continue
        if bid <= 0 and ask <= 0:
            continue
        mids[str(q["code"]).strip()] = (bid + ask) / 2 if (bid > 0 and ask > 0) else max(bid, ask)
    if not mids:
        return Courbe(d, list(base.taux), list(base.lignes), base.source)
    par_ech = {}
    for l in base.lignes:
        par_ech[l.echeance] = Ligne(l.echeance, l.taux, l.code, l.libelle)
    ecarts = []
    for code, m in mids.items():
        t = ref.get(code)
        if not t or t.echeance <= d:
            continue
        anc = par_ech.get(t.echeance)
        if anc:
            ecarts.append(m - anc.taux)
        par_ech[t.echeance] = Ligne(t.echeance, m, code, t.libelle)
    lignes = sorted(par_ech.values(), key=lambda l: l.echeance)
    if regle == "decalage":
        dec = sum(ecarts) / len(ecarts) if ecarts else 0.0
        return Courbe(d, [t + dec for t in base.taux], lignes, f"BKAM du {base.date:%d/%m/%Y} decalee de {dec*1e4:+.1f} pb (eBond)")
    points = [((l.echeance - d).days / 365, l.taux) for l in lignes if 0.01 < (l.echeance - d).days / 365 < 60]
    try:
        taux, note = tenors_depuis_points(points)
    except ValueError:
        return Courbe(d, list(base.taux), lignes, base.source)
    return Courbe(d, taux, lignes, f"BKAM du {base.date:%d/%m/%Y} + {len(mids)} cotations eBond" + (" ; " + note.replace("\n", " ; ") if note else ""))
