"""Courbe de la feuille et lectures d un titre : port de la feuille Valorisation du classeur.

Toutes les interpolations sont des TREND a deux points (droite passant par les deux points : interpole et extrapole).
Conventions : une ligne ou un tenor de maturite <= 365 j porte un taux monetaire (exact/360), au-dela un taux actuariel.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import datetime as dt
from .courbe import Courbe, TENORS, mon_vers_act, act_vers_mon


def trend(x0, y0, x1, y1, x):
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


@dataclass
class LigneFeuille:
    code: str
    libelle: str
    jouissance: dt.date | None
    echeance: dt.date
    jours: int                 # maturite residuelle en jours a la date
    taux_bam: float | None     # taux publie (courbe retenue)
    taux_ebond: float | None   # force a la main ou eBond
    @property
    def retenu(self):
        return self.taux_ebond if self.taux_ebond is not None else self.taux_bam
    @property
    def source(self):
        return "eBond / main" if self.taux_ebond is not None else ("BAM" if self.taux_bam is not None else "-")
    def monetaire(self):
        t = self.retenu
        if t is None or self.jours <= 0:
            return None
        return t if self.jours <= 365 else act_vers_mon(t, self.jours)
    def actuariel(self):
        t = self.retenu
        if t is None or self.jours <= 0:
            return None
        return t if self.jours > 365 else mon_vers_act(t, self.jours)
    def convention(self, residuel_titre: int):
        """Taux de la ligne dans la convention du titre (monetaire si le titre a <= 365 j, actuariel sinon)."""
        return self.monetaire() if residuel_titre <= 365 else self.actuariel()


class CourbeFeuille:
    def __init__(self, courbe: Courbe, ref: dict, d: dt.date, ebond: dict | None = None, hors_bornes: str = "bam"):
        """ebond : dict code -> taux force (decimal). hors_bornes : 'bam' (tenor de la courbe BAM) ou 'extrapolation'."""
        self.courbe = courbe; self.d = d; self.hors_bornes = hors_bornes
        self.lignes: list[LigneFeuille] = []
        ebond = ebond or {}
        for l in courbe.lignes:
            t = ref.get(l.code) if l.code else None
            jours = (l.echeance - d).days
            if jours <= 0:
                continue
            self.lignes.append(LigneFeuille(l.code, t.libelle if t else l.libelle, t.jouissance if t else None, l.echeance, jours, l.taux, ebond.get(l.code)))
        # lignes forcees a la main qui ne sont pas dans la courbe publiee
        for code, tx in ebond.items():
            if code not in {x.code for x in self.lignes} and code in ref and (ref[code].echeance - d).days > 0:
                t = ref[code]
                self.lignes.append(LigneFeuille(code, t.libelle, t.jouissance, t.echeance, (t.echeance - d).days, None, tx))
        self.lignes = [x for x in self.lignes if x.retenu is not None]
        self.lignes.sort(key=lambda x: x.jours)
        self.tenors_retenus: list = list(courbe.taux)        # Q7:Q16 ; modifiables a la main

    # ------------------------------------------------------------ tenors calcules depuis les lignes (P7:P16)
    def tenors_calcules(self) -> list:
        out = []
        n = len(self.lignes)
        for k, (nom, j, conv) in enumerate(TENORS):
            bam = self.courbe.taux[k]
            if n < 2:
                out.append(bam); continue
            jours = [x.jours for x in self.lignes]
            vals = [x.monetaire() if j <= 365 else x.actuariel() for x in self.lignes]
            if j < jours[0] or j > jours[-1]:
                if self.hors_bornes == "bam":
                    out.append(bam); continue
                idx = 0 if j < jours[0] else n - 2
            else:
                idx = max(i for i in range(n) if jours[i] <= j)
                idx = max(0, min(n - 2, idx))
            out.append(trend(jours[idx], vals[idx], jours[idx + 1], vals[idx + 1], j))
        return out

    def tableau_tenors(self) -> list:
        calc = self.tenors_calcules()
        return [dict(tenor=nom, jours=j, maturite=j / 365, calcule=c, retenu=r, ecart_pb=(r - c) * 1e4 if (c is not None and r is not None) else None, convention="monetaire" if j <= 365 else "actuariel")
                for (nom, j, _), c, r in zip(TENORS, calc, self.tenors_retenus)]

    # ------------------------------------------------------------ lecture 1 : tenors
    def lecture_tenors(self, residuel: int, force_bas=None, force_haut=None) -> dict:
        jours = [j for _, j, _ in TENORS]
        if residuel <= 365:
            i = max(0, min(1, max([k for k in range(3) if jours[k] <= residuel] or [0])))
        else:
            i = 3 + max(0, min(5, max([k for k in range(6) if jours[3 + k] <= residuel] or [0])))
        x0, x1 = jours[i], jours[i + 1]
        y0 = force_bas if force_bas is not None else self.tenors_retenus[i]
        y1 = force_haut if force_haut is not None else self.tenors_retenus[i + 1]
        note = ""
        if residuel < jours[0]:
            note = "extrapolation (pente 13-26 sem)"
        elif residuel <= 365 and residuel > jours[2]:
            note = "extrapolation (pente 26-52 sem)"
        elif residuel > jours[-1]:
            note = "extrapolation (pente 20-30 ans)"
        return dict(borne_basse=TENORS[i][0], borne_haute=TENORS[i + 1][0], jours_bas=x0, jours_haut=x1, taux_bas=self.tenors_retenus[i], taux_haut=self.tenors_retenus[i + 1],
                    retenu_bas=y0, retenu_haut=y1, taux=trend(x0, y0, x1, y1, residuel), note=note, convention="monetaire" if residuel <= 365 else "actuariel")

    # ------------------------------------------------------------ lecture 2 : lignes encadrantes
    def encadrantes(self, echeance: dt.date, residuel: int) -> tuple:
        n = len(self.lignes)
        if n < 2:
            return None, None
        pos = max([i for i in range(n) if self.lignes[i].jours <= residuel] or [0])
        exact = 1 if self.lignes[pos].echeance == echeance else 0
        h = max(0, min(n - 2, pos - exact))      # H18
        hh = min(n - 1, max(h + 1, pos + 1))     # H19
        return self.lignes[h], self.lignes[hh]

    def lecture_lignes(self, echeance: dt.date, residuel: int, force_bas=None, force_haut=None) -> dict:
        bas, haut = self.encadrantes(echeance, residuel)
        if bas is None:
            return dict(ok=False, message="moins de deux lignes dans la courbe de la feuille")
        y0 = force_bas if force_bas is not None else bas.convention(residuel)
        y1 = force_haut if force_haut is not None else haut.convention(residuel)
        elle = next((x for x in self.lignes if x.echeance == echeance), None)
        note = "extrapolation" if (residuel < bas.jours or residuel > haut.jours) else ""
        if (residuel <= 365 and haut.jours > 365) or (residuel > 365 and bas.jours <= 365):
            note += (" ; " if note else "") + "une borne change de convention (convertie)"
        return dict(ok=True, bas=bas, haut=haut, taux_bas=bas.convention(residuel), taux_haut=haut.convention(residuel), retenu_bas=y0, retenu_haut=y1,
                    taux=trend(bas.jours, y0, haut.jours, y1, residuel), ligne_elle_meme=elle.retenu if elle else None, note=note)

    # ------------------------------------------------------------ lecture 3 : deux lignes de mon choix
    def taux_ligne_convention(self, code: str, residuel: int):
        """Taux d une ligne de la feuille (ou interpole entre ses voisines si elle n y est pas) dans la convention du titre."""
        x = next((l for l in self.lignes if l.code == code), None)
        if x:
            return x.convention(residuel), x
        return None, None

    def lecture_choix(self, code_bas: str, code_haut: str, residuel: int, force_bas=None, force_haut=None) -> dict:
        t0, l0 = self.taux_ligne_convention(code_bas, residuel); t1, l1 = self.taux_ligne_convention(code_haut, residuel)
        if l0 is None or l1 is None:
            return dict(ok=False, message="choisir deux lignes de la courbe de la feuille")
        y0 = force_bas if force_bas is not None else t0; y1 = force_haut if force_haut is not None else t1
        return dict(ok=True, bas=l0, haut=l1, taux_bas=t0, taux_haut=t1, retenu_bas=y0, retenu_haut=y1, taux=trend(l0.jours, y0, l1.jours, y1, residuel))


def chocs(prix: float, sensi: float, conv: float, qte: float, nominal_unit: float, liste=(-50, -25, -10, 10, 25, 50)) -> list:
    out = []
    for c in liste:
        p = prix * (1 - sensi * c / 1e4 + 0.5 * conv * (c / 1e4) ** 2)
        out.append(dict(choc=c, prix=p, valeur=qte * nominal_unit * (p - prix) / 100))
    return out
