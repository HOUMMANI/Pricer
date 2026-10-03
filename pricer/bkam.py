"""Lecture de la courbe des taux de reference sur le site de Bank Al-Maghrib (port de la macro mdlCourbeBAM)."""
from __future__ import annotations
import re, datetime as dt
from .courbe import Courbe, Ligne, tenors_depuis_points

URL_BASE = ("https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-obligataire/"
            "Marche-des-bons-de-tresor/Marche-secondaire/Taux-de-reference-des-bons-du-tresor")
BLOCK_ID = "e1d6b9bbf87f86f8ba53e8518e882982"
ENTETES = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "fr-FR,fr;q=0.9"}

_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _lire_date(s: str):
    s = s.strip()
    if not _DATE.match(s):
        return None
    j, m, a = s.split("/")
    try:
        return dt.date(int(a), int(m), int(j))
    except ValueError:
        return None


def _lire_taux(s: str):
    buf = "".join(ch for ch in s.replace("%", "").replace("\xa0", "").replace(" ", "").replace(",", ".") if ch.isdigit() or ch == ".")
    if not buf:
        return None
    try:
        v = float(buf)
    except ValueError:
        return None
    if v > 1:
        v = v / 100
    if v <= 0 or v >= 0.5:
        return None
    return round(v, 6)


def _nettoyer(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ").replace("&#160;", " ")
    return re.sub(r"\s+", " ", s).strip()


def extraire_points(contenu: str) -> list:
    """Retourne [(echeance, date_courbe, taux)] : premiere date = echeance, derniere = date de la courbe, premier nombre = taux."""
    pts = []
    if "<tr" in contenu.lower():
        lignes = re.split(r"<tr", contenu, flags=re.I)
        for lg in lignes:
            cel = [_nettoyer(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", lg, flags=re.I | re.S)]
            p = _lire_cellules(cel)
            if p:
                pts.append(p)
    else:
        for lg in contenu.replace("\r", "").split("\n"):
            sep = ";" if lg.count(";") >= 2 else ("\t" if lg.count("\t") >= 2 else ",")
            p = _lire_cellules([c.strip().strip('"') for c in lg.split(sep)])
            if p:
                pts.append(p)
    return pts


def _lire_cellules(cel: list):
    dEch = dVal = None; taux = None; nd = 0
    for c in cel:
        d = _lire_date(c)
        if d:
            nd += 1
            if nd == 1:
                dEch = d
            dVal = d
        elif taux is None:
            taux = _lire_taux(c)
    if nd >= 2 and dEch != dVal and taux:
        return (dEch, dVal, taux)
    return None


def telecharger(date: dt.date | None = None, timeout: int = 20) -> str:
    import requests
    params = {}
    if date:
        params = {"date": date.strftime("%d/%m/%Y"), "block": BLOCK_ID}
    r = requests.get(URL_BASE, params=params, headers=ENTETES, timeout=timeout)
    r.raise_for_status()
    return r.text


def courbe_depuis_contenu(contenu: str, ref: dict | None = None) -> Courbe:
    pts = extraire_points(contenu)
    if len(pts) < 2:
        raise ValueError("aucun point de courbe lisible dans le contenu")
    dval = max(p[1] for p in pts)
    pts = [p for p in pts if p[1] == dval]
    points = [((e - dval).days / 365, t) for e, _, t in pts if 0.01 < (e - dval).days / 365 < 60]
    taux, note = tenors_depuis_points(points)
    par_ech = {}
    if ref:
        for t in ref.values():
            par_ech.setdefault(t.echeance, t)
    lignes = []
    for e, _, t in sorted(pts):
        tt = par_ech.get(e)
        lignes.append(Ligne(e, t, tt.code if tt else "", tt.libelle if tt else ""))
    c = Courbe(dval, taux, lignes, "BKAM" + (" - " + note if note else ""))
    return c


def courbe_bkam(date: dt.date | None = None, ref: dict | None = None) -> Courbe:
    return courbe_depuis_contenu(telecharger(date), ref)
