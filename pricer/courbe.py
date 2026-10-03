"""Courbe de reference BAM : tenors, conventions, lignes publiees, lectures."""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt
from typing import Optional

TENORS = [("13 semaines", 91, "monetaire"), ("26 semaines", 182, "monetaire"), ("52 semaines", 364, "monetaire (364 j)"),
          ("2 ans", 731, "actuariel"), ("5 ans", 1826, "actuariel"), ("10 ans", 3653, "actuariel"),
          ("15 ans", 5479, "actuariel"), ("20 ans", 7305, "actuariel"), ("30 ans", 10958, "actuariel")]
CLES = ["13s", "26s", "52s", "2a", "5a", "10a", "15a", "20a", "30a"]


def mon_vers_act(r: float, jours: int) -> float:
    """Taux monetaire exact/360 sur `jours` -> taux actuariel annuel (365 j)."""
    return (1 + r * jours / 360) ** (365 / jours) - 1


def act_vers_mon(r: float, jours: int) -> float:
    return ((1 + r) ** (jours / 365) - 1) * 360 / jours


@dataclass
class Ligne:
    echeance: dt.date
    taux: float            # tel que publie (monetaire sous un an, actuariel au-dela)
    code: str = ""
    libelle: str = ""


@dataclass
class Courbe:
    date: dt.date
    taux: list              # 9 taux publies (decimal), convention de place
    lignes: list = field(default_factory=list)   # lignes publiees, triees par echeance
    source: str = ""

    # ---------- tenors
    def actuariels(self) -> list:
        """Les 9 tenors convertis en actuariel annuel (colonne G du classeur)."""
        out = []
        for (nom, j, conv), r in zip(TENORS, self.taux):
            out.append(mon_vers_act(r, j) if conv.startswith("monetaire") else r)
        return out

    def tableau(self) -> list:
        return [dict(tenor=n, jours=j, maturite=j / 365, convention=c, publie=r, actuariel=a)
                for (n, j, c), r, a in zip(TENORS, self.taux, self.actuariels())]

    # ---------- lecture 1 : interpolation sur les tenors (convention du titre)
    def taux_tenors(self, residuel_jours: int) -> tuple:
        """Interpolation lineaire en jours entre les deux tenors encadrants, dans la convention du titre :
        monetaire (13, 26, 52 sem) jusqu a 365 j, actuariel (2 a 30 ans) au-dela. Extrapolation par la paire de bord."""
        jours = [j for _, j, _ in TENORS]
        if residuel_jours <= 365:
            noeuds = list(zip(jours[0:3], self.taux[0:3]))
        else:
            noeuds = list(zip(jours[3:], self.taux[3:]))
        i = 0
        for k in range(len(noeuds) - 1):
            if residuel_jours >= noeuds[k][0]:
                i = k
        (x0, y0), (x1, y1) = noeuds[i], noeuds[i + 1]
        t = y0 + (y1 - y0) * (residuel_jours - x0) / (x1 - x0)
        note = ""
        if residuel_jours < noeuds[0][0] or residuel_jours > noeuds[-1][0]:
            note = "extrapolation"
        return t, (x0, y0, x1, y1), note

    # ---------- lecture 2 : lignes publiees (methode 1 du portefeuille : taux de la ligne, sinon interpolation entre lignes)
    def taux_lignes(self, echeance: dt.date, maturite_ans: float) -> tuple:
        if not self.lignes:
            return None, "aucune ligne publiee"
        for l in self.lignes:
            if l.echeance == echeance:
                return l.taux, "taux publie de la ligne"
        mats = [(l.echeance - self.date).days / 365 for l in self.lignes]
        n = len(self.lignes)
        if n == 1:
            return self.lignes[0].taux, "une seule ligne"
        idx = 0
        for k in range(n):
            if mats[k] <= maturite_ans:
                idx = k
        idx = max(0, min(n - 2, idx))
        y0, y1 = self.lignes[idx].taux, self.lignes[idx + 1].taux
        x0, x1 = mats[idx], mats[idx + 1]
        t = y0 + (maturite_ans - x0) * (y1 - y0) / (x1 - x0) if x1 != x0 else y0
        note = "interpolation entre lignes" if x0 <= maturite_ans <= x1 else "extrapolation entre lignes"
        return t, note

    def taux_pour(self, echeance: dt.date, d: dt.date, methode: str = "lignes") -> tuple:
        residuel = (echeance - d).days
        if methode == "lignes" and self.lignes:
            t, note = self.taux_lignes(echeance, residuel / 365)
            if t is not None:
                return t, note
        t, _, note = self.taux_tenors(residuel)
        return t, "interpolation sur les tenors" + (" (" + note + ")" if note else "")


def interpoler_points(cible: float, mats: list, tx: list) -> float:
    """Interpolation lineaire des points publies (port de la macro) : pente des deux premiers points en deca, plat au-dela."""
    n = len(mats)
    if n == 0:
        return 0.0
    if cible < mats[0]:
        j = 1
        while j < n - 1 and mats[j] <= mats[0]:
            j += 1
        v = tx[0] + (cible - mats[0]) * (tx[j] - tx[0]) / (mats[j] - mats[0]) if (n >= 2 and mats[j] > mats[0]) else tx[0]
        return min(0.2, max(0.0001, v))
    if cible >= mats[-1]:
        return tx[-1]
    for i in range(n - 1):
        if mats[i] <= cible <= mats[i + 1]:
            return tx[i] if mats[i + 1] == mats[i] else tx[i] + (cible - mats[i]) * (tx[i + 1] - tx[i]) / (mats[i + 1] - mats[i])
    return tx[-1]


def tenors_depuis_points(points: list) -> tuple:
    """Points (maturite en annees, taux publie) -> 9 tenors (port de ExtraireTaux + CompleterTenorsManquants).
    Retourne (taux, note)."""
    pts = sorted(points)
    mats = [m for m, _ in pts]; tx = [t for _, t in pts]
    n = len(pts)
    if n < 2:
        raise ValueError("moins de deux points publies")
    cibles = [j / 365 for _, j, _ in TENORS]
    jj = n - 2
    while jj > 0 and mats[-1] - mats[jj] < 3:
        jj -= 1
    pente = (tx[-1] - tx[jj]) / (mats[-1] - mats[jj]) if (jj >= 0 and mats[-1] > mats[jj]) else 0.0
    pente = max(-0.002, min(0.002, pente))
    taux = []
    for c in cibles:
        conv = []
        for m, t in zip(mats, tx):
            j = max(m * 365, 1)
            if c <= 1.0:
                conv.append(((1 + t) ** (j / 365) - 1) * 360 / j if j > 365 else t)
            else:
                conv.append((1 + t * j / 360) ** (365 / j) - 1 if j <= 365 else t)
        taux.append(interpoler_points(c, mats, conv))
    notes = []
    for k, c in enumerate(cibles):
        if c > mats[-1] + 0.05:
            v = min(0.2, max(0.0001, tx[-1] + pente * (c - mats[-1])))
            taux[k] = v
            notes.append(f"{TENORS[k][0]} extrapole a {v:.3%} (pente {pente*1e4:+.1f} pb/an au-dela de {mats[-1]:.2f} ans)")
    return taux, "\n".join(notes)
