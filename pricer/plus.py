"""Radar des clients, courbe des ordres, memoire des negociations, resume du jour, alertes."""
from __future__ import annotations
import datetime as dt
from collections import defaultdict
from .carnet import valable, tenor_de, matchs
from .courbe import TENORS

BUCKETS = [("13s", 0.25), ("26s", 0.5), ("52s", 1), ("2 ans", 2), ("5 ans", 5), ("10 ans", 10), ("15 ans", 15), ("20 ans", 20), ("30 ans", 30)]


def bucket(tenor_ans):
    if tenor_ans is None:
        return None
    return min(BUCKETS, key=lambda b: abs(b[1] - tenor_ans))[0]


# ------------------------------------------------------------------ 1 radar des clients
def radar(flux: list, ref: dict, aujourdhui: dt.date) -> list:
    par = defaultdict(lambda: dict(ordres=0, achats=0.0, ventes=0.0, tenors=defaultdict(float), tailles=[], dernier=None, valables=0))
    for f in flux:
        c = f.get("contrepartie")
        if not c:
            continue
        try:
            d = dt.date.fromisoformat(f["date"]); n = float(f.get("nominal") or 0)
        except Exception:
            continue
        p = par[c]; p["ordres"] += 1; p["tailles"].append(n)
        if f.get("sens") == "Achat": p["achats"] += n
        else: p["ventes"] += n
        b = bucket(tenor_de(f, ref, aujourdhui))
        if b: p["tenors"][b] += n
        p["dernier"] = max(p["dernier"], d) if p["dernier"] else d
        if valable(f, aujourdhui): p["valables"] += 1
    out = []
    for c, p in par.items():
        top = sorted(p["tenors"].items(), key=lambda kv: -kv[1])[:3]
        out.append(dict(client=c, ordres=p["ordres"], valables=p["valables"], achats=p["achats"], ventes=p["ventes"], net=p["achats"] - p["ventes"],
                        taille_moyenne=sum(p["tailles"]) / len(p["tailles"]) if p["tailles"] else 0, tenors=", ".join(f"{t} ({v/1e6:.0f} M)" for t, v in top),
                        dernier=p["dernier"], profil="acheteur" if p["achats"] > 1.5 * p["ventes"] else ("vendeur" if p["ventes"] > 1.5 * p["achats"] else "les deux")))
    out.sort(key=lambda x: -(x["achats"] + x["ventes"]))
    return out


def placer(flux: list, ref: dict, aujourdhui: dt.date, sens_client: str, tenor_ans: float, nominal: float) -> list:
    """Qui appeler pour placer (sens_client = Achat : clients acheteurs) ou pour trouver du papier (Vente)."""
    score = defaultdict(lambda: dict(score=0.0, raisons=[], dispo=0.0))
    for f in flux:
        c = f.get("contrepartie")
        if not c or f.get("sens") != sens_client:
            continue
        t = tenor_de(f, ref, aujourdhui)
        if t is None or abs(t - tenor_ans) > (0.3 if tenor_ans < 1.5 else 1.5):
            continue
        try:
            d = dt.date.fromisoformat(f["date"]); n = float(f.get("nominal") or 0)
        except Exception:
            continue
        age = (aujourdhui - d).days
        s = score[c]
        if valable(f, aujourdhui):
            s["score"] += 10 + n / 1e8; s["dispo"] += n; s["raisons"].append(f"ordre valable {n/1e6:.0f} M du {d:%d/%m}" + (f" a {float(f['taux'])*100:.2f} %" if f.get("taux") else ""))
        else:
            s["score"] += max(0.5, 5 - age / 30); s["raisons"].append(f"{sens_client.lower()} {n/1e6:.0f} M le {d:%d/%m}")
    out = [dict(client=c, score=round(v["score"], 1), disponible=v["dispo"], raisons=" ; ".join(v["raisons"][-3:])) for c, v in score.items()]
    out.sort(key=lambda x: -x["score"])
    return out


# ------------------------------------------------------------------ 2 courbe des ordres
def courbe_des_ordres(flux: list, ref: dict, aujourdhui: dt.date, courbe=None, ebond: list | None = None) -> list:
    acc = defaultdict(lambda: dict(achat=[], vente=[]))
    for f in flux:
        if not valable(f, aujourdhui) or not f.get("taux"):
            continue
        b = bucket(tenor_de(f, ref, aujourdhui))
        if b:
            acc[b]["achat" if f.get("sens") == "Achat" else "vente"].append((float(f["taux"]), float(f.get("nominal") or 0)))
    eb = defaultdict(list)
    for q in ebond or []:
        t = ref.get(str(q.get("code", "")).strip())
        if not t: continue
        try:
            bid, ask = float(q.get("bid") or 0), float(q.get("ask") or 0)
        except ValueError:
            continue
        m = (bid + ask) / 2 if bid and ask else max(bid, ask)
        if m: eb[bucket((t.echeance - aujourdhui).days / 365)].append(m)
    out = []
    for k, (nom, _, _) in enumerate(TENORS):
        b = BUCKETS[k][0]
        a, v = acc[b]["achat"], acc[b]["vente"]
        wm = lambda L: sum(t * n for t, n in L) / sum(n for _, n in L) if L and sum(n for _, n in L) else None
        ta, tv = wm(a), wm(v)
        implicite = (ta + tv) / 2 if (ta is not None and tv is not None) else (ta if ta is not None else tv)
        bam = courbe.taux[k] if courbe else None
        ebm = sum(eb[b]) / len(eb[b]) if eb.get(b) else None
        out.append(dict(tenor=nom, acheteurs=ta, vendeurs=tv, nb_achats=len(a), nb_ventes=len(v), implicite=implicite, bam=bam, ebond=ebm,
                        ecart_bam_pb=(implicite - bam) * 1e4 if (implicite is not None and bam is not None) else None))
    return out


# ------------------------------------------------------------------ 3 memoire des negociations
def memoire(operations: list, flux: list, ref: dict, code: str, client: str, aujourdhui: dt.date) -> dict:
    donnes = [o for o in operations if o.get("contrepartie") == client and o.get("code") == code]
    demandes = [f for f in flux if f.get("contrepartie") == client and f.get("code") == code]
    meme_tenor = []
    if code in ref:
        tn = (ref[code].echeance - aujourdhui).days / 365
        meme_tenor = [o for o in operations if o.get("contrepartie") == client and o.get("code") in ref and o.get("code") != code and abs((ref[o["code"]].echeance - aujourdhui).days / 365 - tn) <= 1.5]
    return dict(donnes=sorted(donnes, key=lambda o: o["date"], reverse=True)[:6], demandes=sorted(demandes, key=lambda f: f["date"], reverse=True)[:6],
                meme_tenor=sorted(meme_tenor, key=lambda o: o["date"], reverse=True)[:4],
                taux_ratio=f"{len(donnes)} operation(s) pour {len(demandes)} ordre(s)" if demandes else f"{len(donnes)} operation(s)")


# ------------------------------------------------------------------ 5 resume du jour
def resume_jour(store, ref: dict, aujourdhui: dt.date, courbe, pnl_rows: list | None, fmt_pct, fmt_mnt) -> tuple:
    courbes = store.courbes(); prev = sorted(x for x in courbes if courbe and x < courbe.date)
    L = [f"Resume du {aujourdhui:%d/%m/%Y}", ""]
    if courbe:
        L.append(f"Courbe BAM du {courbe.date:%d/%m/%Y}" + (f" (vs {prev[-1]:%d/%m/%Y})" if prev else ""))
        for k, (nom, _, _) in enumerate(TENORS):
            v = courbe.taux[k]; s = f"  {nom:12} {fmt_pct(v)}"
            if prev: s += f"  {(v - courbes[prev[-1]][0][k])*1e4:+.1f} pb"
            L.append(s)
        L.append("")
    ops = [o for o in store.operations() if o.get("date") == aujourdhui.isoformat()]
    L.append(f"Operations du jour : {len(ops)}")
    for o in ops:
        t = ref.get(o["code"]); L.append(f"  {o['sens']} {fmt_mnt(float(o['nominal']))} MAD {t.libelle if t else o['code']} a {fmt_pct(float(o['taux']))} - {o.get('contrepartie', '')}")
    L.append("")
    if pnl_rows:
        r = pnl_rows[-1]; L.append(f"P&L {r['de']:%d/%m} -> {r['a']:%d/%m} : {fmt_mnt(r['total'])} MAD (carry {fmt_mnt(r['carry'])}, courbe {fmt_mnt(r['effet_courbe'])}, trading {fmt_mnt(r['trading'])}, financement {fmt_mnt(r['financement'])})"); L.append("")
    flux = store.flux(); val = [f for f in flux if valable(f, aujourdhui)]
    L.append(f"Ordres valables : {len(val)}")
    for f in val[:15]:
        t = ref.get(f.get("code", "")); lib = t.libelle if t else (f"interet {f['tenor']} ans" if f.get("tenor") else "")
        L.append(f"  {f['contrepartie']} {f['sens'].lower()} {float(f['nominal'] or 0)/1e6:.0f} M {lib}" + (f" a {float(f['taux'])*100:.2f} %" if f.get("taux") else "") + f" (du {dt.date.fromisoformat(f['date']):%d/%m})")
    L.append("")
    mm = matchs(flux, ref, aujourdhui, 7)
    L.append(f"Matchs possibles : {len(mm)}")
    for m in mm[:8]:
        L.append(f"  {m['verdict']} : {m['acheteur']} achete / {m['vendeur']} vend {m['nominal']/1e6:.0f} M ({m['nature']})" + (f", ecart {m['ecart_pb']:+.1f} pb" if m['ecart_pb'] is not None else ""))
    return f"Resume du jour - {aujourdhui:%d/%m/%Y}", "\n".join(L)


# ------------------------------------------------------------------ 6 alertes
def alertes(store, ref: dict, aujourdhui: dt.date, limites_rows: list, ebond: list, seuil=0.8) -> list:
    out = []
    for x in limites_rows:
        if x["utilisation"] >= 1: out.append(("rouge", f"Limite depassee : {x['palier']} a {x['utilisation']:.0%}"))
        elif x["utilisation"] >= seuil: out.append(("orange", f"Limite a {x['utilisation']:.0%} : {x['palier']}"))
    flux = store.flux()
    for f in flux:
        if not valable(f, aujourdhui): continue
        try:
            d = dt.date.fromisoformat(f["date"])
        except Exception:
            continue
        reste = 30 - (aujourdhui - d).days
        if 0 <= reste <= 2:
            t = ref.get(f.get("code", "")); out.append(("orange", f"Ordre qui expire dans {reste} j : {f['contrepartie']} {f['sens'].lower()} {float(f['nominal'] or 0)/1e6:.0f} M {t.libelle if t else ''}"))
    for m in matchs(flux, ref, aujourdhui, 7):
        if m["verdict"] == "croisable":
            out.append(("vert", f"Match croisable : {m['acheteur']} / {m['vendeur']} {m['nominal']/1e6:.0f} M, ecart {m['ecart_pb']:+.1f} pb"))
    # eBond qui croise un ordre client
    quotes = {str(q.get("code", "")).strip(): q for q in ebond or []}
    for f in flux:
        if not valable(f, aujourdhui) or not f.get("taux") or f.get("code") not in quotes: continue
        q = quotes[f["code"]]; yc = float(f["taux"])
        try:
            bid, ask = float(q.get("bid") or 0), float(q.get("ask") or 0)
        except ValueError:
            continue
        t = ref.get(f["code"])
        if f["sens"] == "Achat" and ask and ask >= yc:
            out.append(("vert", f"eBond croise un achat client : acheter sur eBond a {ask*100:.2f} %, vendre a {f['contrepartie']} a {yc*100:.2f} % ({t.libelle if t else ''}, {(ask-yc)*1e4:+.1f} pb)"))
        if f["sens"] == "Vente" and bid and bid <= yc:
            out.append(("vert", f"eBond croise une vente client : acheter a {f['contrepartie']} a {yc*100:.2f} %, vendre sur eBond a {bid*100:.2f} % ({t.libelle if t else ''}, {(yc-bid)*1e4:+.1f} pb)"))
    return out
