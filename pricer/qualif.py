"""Qualification des operations : intermediation, compte propre, eBond, swap, marche primaire (pour moi ou pour une contrepartie)."""
from __future__ import annotations
import datetime as dt

NATURES = ["Intermediation", "Compte propre", "eBond", "Swap", "Primaire compte propre", "Primaire pour contrepartie"]
CANAUX = ["Marche", "eBond", "Primaire"]


def _d(o, cle="date"):
    try:
        return dt.date.fromisoformat(o.get(cle) or o["date"])
    except Exception:
        return None


def _n(o):
    try:
        return float(o.get("nominal") or 0)
    except ValueError:
        return 0.0


def qualifier(ops: list, ref: dict, delai_jours: int = 5, tol: float = 0.01) -> list:
    """Retourne une copie des operations avec 'nature' et, pour les paires, 'intermediation_id' / 'swap_id' / 'primaire_id'.
    Les natures deja fixees a la main (champ nature_fixe = 1 dans commentaire ? non) : une nature existante commencant par '!' est conservee."""
    out = [dict(o) for o in ops if not o.get("parent_id")]
    vent = [dict(o) for o in ops if o.get("parent_id")]
    pris = set()
    def canal(o): return (o.get("canal") or "Marche").strip().lower()
    # 1 - intermediations declarees
    for o in out:
        if o.get("intermediation_id"):
            o["nature"] = "Intermediation"; pris.add(o["id"])
    # 2 - swaps : meme contrepartie, codes differents, un achat et une vente, sous delai, nominal egal ou sensi egale
    def _pvbp(o):
        t = ref.get(o.get("code", "")) if ref else None
        try:
            if t and o.get("taux") and _d(o):
                from .bdt import valoriser
                v = valoriser(t, _d(o), float(o["taux"])); return v.sensi * _n(o) * v.prix_plein / 100 * 1e-4
        except Exception:
            return None
        return None
    for a in out:
        if a["id"] in pris or a["sens"] != "Achat" or canal(a) != "marche": continue
        for v in sorted(out, key=lambda x: x["date"]):
            if v["id"] in pris or v["sens"] != "Vente" or v["code"] == a["code"] or v.get("contrepartie") != a.get("contrepartie") or canal(v) != "marche": continue
            if not (_d(a) and _d(v)) or abs((_d(v) - _d(a)).days) > delai_jours: continue
            egal_nom = abs(_n(a) - _n(v)) <= tol * max(_n(a), 1)
            pa, pv = _pvbp(a), _pvbp(v)
            egal_sensi = pa is not None and pv is not None and pa > 0 and abs(pa - pv) <= 0.1 * pa
            if egal_nom or egal_sensi:
                sid = "S" + a["id"]; a["nature"] = v["nature"] = "Swap" + ("" if egal_nom else " (sensi egale)"); a["swap_id"] = v["swap_id"] = sid; pris.update({a["id"], v["id"]}); break
    # 3 - primaire pour une contrepartie : achat en primaire puis vente du meme titre, meme nominal, a un tiers, sous delai
    for a in out:
        if a["id"] in pris or a["sens"] != "Achat" or canal(a) != "primaire": continue
        for v in sorted(out, key=lambda x: x["date"]):
            if v["id"] in pris or v["sens"] != "Vente" or v["code"] != a["code"]: continue
            if _d(v) and _d(a) and 0 <= (_d(v) - _d(a)).days <= delai_jours and abs(_n(a) - _n(v)) <= tol * max(_n(a), 1):
                pid = "P" + a["id"]; a["nature"] = v["nature"] = "Primaire pour contrepartie"; a["primaire_id"] = v["primaire_id"] = pid; pris.update({a["id"], v["id"]}); break
    # 4 - intermediations : des vendeurs vers des acheteurs, en nombre quelconque de chaque cote ;
    #     meme titre, somme des achats = somme des ventes, sous delai, tiers differents entre les deux cotes ;
    #     l ordre est libre : la vente peut preceder l achat (on puise dans le portefeuille)
    from itertools import combinations
    def _sommes(L, kmax=12):
        L = L[:kmax]; out = {}
        for k in range(1, len(L) + 1):
            for comb in combinations(L, k):
                out.setdefault(round(sum(_n(c) for c in comb), -3), []).append(comb)
        return out
    codes = sorted({o["code"] for o in out if o["id"] not in pris and canal(o) == "marche"})
    for code in codes:
        while True:
            A = sorted([o for o in out if o["id"] not in pris and not o.get("_libre") and o["code"] == code and o["sens"] == "Achat" and canal(o) == "marche" and _d(o)], key=lambda x: x["date"])
            V = sorted([o for o in out if o["id"] not in pris and not o.get("_libre") and o["code"] == code and o["sens"] == "Vente" and canal(o) == "marche" and _d(o)], key=lambda x: x["date"])
            if not A or not V: break
            d0 = min(_d(A[0]), _d(V[0])); fin_ = d0 + dt.timedelta(days=delai_jours)
            Aw = [a for a in A if _d(a) <= fin_]; Vw = [v for v in V if _d(v) <= fin_]
            tiersA = {a.get("contrepartie") for a in Aw}
            Vw = [v for v in Vw if v.get("contrepartie") not in tiersA or not v.get("contrepartie")]
            if not Aw or not Vw:
                min(A + V, key=lambda x: x["date"])["_libre"] = True; continue
            sa, sv = _sommes(Aw), _sommes(Vw)
            meilleur = None
            for s_, combsA in sa.items():
                for s2, combsV in sv.items():
                    if abs(s_ - s2) <= tol * max(s_, 1):
                        for ca in combsA:
                            for cv in combsV:
                                # vente avant achat admise : on puise dans le portefeuille, on rachete ensuite
                                score = (s_, -(len(ca) + len(cv)))
                                if meilleur is None or score > meilleur[0]: meilleur = (score, ca, cv)
            if not meilleur:
                min(Aw + Vw, key=lambda x: x["date"])["_libre"] = True; continue
            _, ca, cv = meilleur; iid = "I" + ca[0]["id"]
            for x in list(ca) + list(cv):
                x["nature"] = "Intermediation"; x["intermediation_id"] = iid; pris.add(x["id"])
    for o in out: o.pop("_libre", None)
    # 5 - le reste
    for o in out:
        if o["id"] in pris: continue
        c = canal(o)
        o["nature"] = "eBond" if c == "ebond" else ("Primaire compte propre" if c == "primaire" else "Compte propre")
    for v in vent:
        p = next((o for o in out if o["id"] == v.get("parent_id")), None)
        v["nature"] = (p["nature"] + " (ventilation)") if p else "Ventilation"
    return out + vent


def resume(qualifiees: list) -> list:
    acc = {}
    for o in qualifiees:
        if o.get("parent_id"): continue
        k = o.get("nature", "?"); a = acc.setdefault(k, dict(nature=k, nb=0, achats=0.0, ventes=0.0))
        a["nb"] += 1
        if o["sens"] == "Achat": a["achats"] += _n(o)
        else: a["ventes"] += _n(o)
    return sorted(acc.values(), key=lambda x: -x["nb"])
