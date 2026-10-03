"""Le carnet de l equipe : comprendre un ordre ecrit en francais, par regles, sans modele."""
from __future__ import annotations
import re, datetime as dt

SENS = {"achete": "Achat", "achète": "Achat", "achat": "Achat", "acheteur": "Achat", "prend": "Achat", "paie": "Achat", "offre": "Vente",
        "vend": "Vente", "vente": "Vente", "vendeur": "Vente", "cede": "Vente", "cède": "Vente"}
TENORS_ANS = {"13s": 0.25, "26s": 0.5, "52s": 1, "2 ans": 2, "5 ans": 5, "10 ans": 10, "15 ans": 15, "20 ans": 20, "30 ans": 30}
MOIS = {"janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _nombre(txt: str):
    return float(txt.replace(" ", "").replace(",", "."))


def lire_nominal(msg: str):
    """'150 M', '150 MMAD', '150 millions', '1,5 Mrd', '100000000' -> MAD."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mrd|milliards?|mmad|millions?|m)\b", msg, re.I)
    if m:
        v = _nombre(m.group(1)); u = m.group(2).lower()
        return v * (1e9 if u.startswith("m") and (u.startswith("mrd") or u.startswith("milliard")) else 1e6), m.group(0)
    m = re.search(r"\b(\d{7,12})\b", msg.replace(" ", ""))
    if m:
        return float(m.group(1)), m.group(1)
    return None, ""


def lire_taux(msg: str):
    m = re.search(r"(?:à|a|@|au taux de|taux)\s*(\d{1,2}[.,]\d{1,3})\s*%?", msg, re.I)
    if m:
        return _nombre(m.group(1)) / 100, m.group(0)
    m = re.search(r"(\d{1,2}[.,]\d{1,3})\s*%", msg)
    if m:
        return _nombre(m.group(1)) / 100, m.group(0)
    return None, ""


TENOR_JOURS = {0.25: 91, 0.5: 182, 1: 364, 2: 731, 5: 1826, 10: 3653, 15: 5479, 20: 7305, 30: 10958}


def lire_cotations_tenors(msg: str) -> dict:
    """'2 ans a 2,55 et 5 ans a 3,02' -> {2: 0.0255, 5: 0.0302} ; '26 semaines a 2,2' -> {0.5: 0.022}."""
    out = {}
    for m in re.finditer(r"(\d{1,2})\s*(ans|an|semaines|sem|s)\b\s*(?:à|a|@|:)?\s*(\d{1,2}[.,]\d{1,3})\s*%?", msg, re.I):
        n = int(m.group(1)); u = m.group(2).lower()
        annees = n if u.startswith("an") else n / 52
        cle = min(TENOR_JOURS, key=lambda k: abs(k - annees))
        out[cle] = _nombre(m.group(3)) / 100
    return out


def lire_tenor(msg: str):
    m = re.search(r"\b(\d{1,2})\s*(ans|an|semaines|sem)\b", msg, re.I)
    if not m:
        return None
    n = int(m.group(1)); u = m.group(2).lower()
    return n if u.startswith("an") else round(n / 52, 2)


def taux_depuis_tenors(residuel_jours: int, cot: dict) -> tuple:
    """Taux de la ligne a partir des cotations par tenor : un seul tenor -> ce taux ; deux ou plus -> interpolation
    lineaire en jours entre les deux tenors qui encadrent (ou les deux plus proches)."""
    if not cot:
        return None, ""
    if len(cot) == 1:
        k, v = next(iter(cot.items()))
        return v, f"cote au tenor {k:g} ans"
    pts = sorted((TENOR_JOURS[k], v, k) for k, v in cot.items())
    bas = [p for p in pts if p[0] <= residuel_jours]; haut = [p for p in pts if p[0] >= residuel_jours]
    if bas and haut:
        (x0, y0, k0), (x1, y1, k1) = bas[-1], haut[0]
    else:
        (x0, y0, k0), (x1, y1, k1) = (pts[0], pts[1]) if not bas else (pts[-2], pts[-1])
    if x1 == x0:
        return y0, f"cote au tenor {k0:g} ans"
    return y0 + (y1 - y0) * (residuel_jours - x0) / (x1 - x0), f"interpole entre {k0:g} et {k1:g} ans"


def lire_prix(msg: str):
    m = re.search(r"(?:prix|px)\s*(\d{2,3}[.,]\d{1,4})", msg, re.I)
    return (_nombre(m.group(1)), m.group(0)) if m else (None, "")


def lire_date_op(msg: str, aujourdhui: dt.date):
    low = msg.lower()
    if "hier" in low:
        return aujourdhui - dt.timedelta(days=1)
    if "avant-hier" in low:
        return aujourdhui - dt.timedelta(days=2)
    m = re.search(r"\ble\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", low)
    if m:
        j, mo = int(m.group(1)), int(m.group(2)); a = int(m.group(3)) if m.group(3) else aujourdhui.year
        if a < 100: a += 2000
        try:
            return dt.date(a, mo, j)
        except ValueError:
            pass
    return aujourdhui


def lire_ligne(msg: str, ref: dict, aujourdhui: dt.date):
    """Retourne (code, candidats, texte_reconnu). candidats > 1 : ambigu."""
    vivants = {k: t for k, t in ref.items() if t.echeance > aujourdhui}
    pref = lambda ks: sorted(ks, key=lambda k: (0 if "BDT" in ref[k].libelle.upper() else 1, -int(k) if k.isdigit() else 0))
    m = re.search(r"\b(\d{6})\b", msg)
    if m and m.group(1) in vivants:
        return m.group(1), [m.group(1)], m.group(0)
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", msg)
    if m:
        j, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3)); a = a + 2000 if a < 100 else a
        try:
            e = dt.date(a, mo, j)
            ks = pref([k for k, t in vivants.items() if t.echeance == e])
            if ks:
                return (ks[0] if len(ks) == 1 else None), ks, m.group(0)
        except ValueError:
            pass
    m = re.search(r"\b(?:du|le|la ligne|ligne)\s+(?:(\w+)\s+)?(20\d\d)\b", msg, re.I)
    if m:
        a = int(m.group(2)); mo = MOIS.get((m.group(1) or "").lower())
        ks = pref([k for k, t in vivants.items() if t.echeance.year == a and (mo is None or t.echeance.month == mo)])
        if ks:
            return (ks[0] if len(ks) == 1 else None), ks, m.group(0)
    m = re.search(r"\b(\d{1,2})\s*ans\b", msg, re.I)
    if m:
        n = int(m.group(1))
        ks = sorted([k for k, t in vivants.items() if abs((t.echeance - aujourdhui).days / 365 - n) <= 1.0], key=lambda k: abs((vivants[k].echeance - aujourdhui).days / 365 - n))
        if ks:
            return (ks[0] if len(ks) == 1 else None), ks[:6], m.group(0)
    return None, [], ""


def lire_contrepartie(msg: str, contacts: list, sens_txt: str):
    noms = sorted({c["contrepartie"] for c in contacts if c.get("contrepartie")}, key=len, reverse=True)
    low = msg.lower()
    for n in noms:
        if n.lower() in low:
            return n
    # ce qui precede le verbe
    if sens_txt:
        avant = msg[:msg.lower().find(sens_txt.lower())].strip(" ,:;-")
        avant = re.sub(r"^(?:le|la|les|un|une)\s+", "", avant, flags=re.I)
        if 2 <= len(avant) <= 40 and not re.search(r"\d", avant):
            return avant.strip()
    return None


def comprendre(msg: str, ref: dict, contacts: list, aujourdhui: dt.date, en_cours: dict | None = None) -> dict:
    """Analyse un message. Retourne dict(ordre=..., manque=[...], question=str, ambigu=[codes]).
    en_cours : ordre incomplet precedent, que ce message complete."""
    msg = _norm(msg)
    o = dict(en_cours or {})
    sens_txt = ""
    for mot, s in SENS.items():
        if re.search(r"\b" + mot + r"\b", msg, re.I):
            o["sens"] = s; sens_txt = mot; break
    cp = lire_contrepartie(msg, contacts, sens_txt)
    if cp and "contrepartie" not in o:
        o["contrepartie"] = cp
    cot = lire_cotations_tenors(msg)
    if cot:
        o["cotations"] = {**o.get("cotations", {}), **cot}
    ten = lire_tenor(msg)
    if ten and "tenor" not in o:
        o["tenor"] = ten
    code, cands, _ = lire_ligne(msg, ref, aujourdhui)
    if code:
        o["code"] = code
    elif cands and "code" not in o:
        o["ambigu"] = cands
    if re.search(r"\b(aucune|pas de ligne|interet|intérêt|pas encore|sans ligne)\b", msg, re.I) and o.get("tenor"):
        o["code"] = ""; o.pop("ambigu", None)                    # interet sur le tenor, ligne a preciser plus tard
    nom, _ = lire_nominal(msg)
    if nom and "nominal" not in o:
        o["nominal"] = nom
    tx, _ = lire_taux(msg)
    if tx and "taux" not in o and not o.get("cotations"):
        o["taux"] = tx; o["mode"] = "ligne cotee directement"
    px, _ = lire_prix(msg)
    if px and "prix" not in o:
        o["prix"] = px
    if "date" not in o:
        o["date"] = lire_date_op(msg, aujourdhui)
    # reponse courte a une question en cours
    if en_cours:
        est_code = bool(re.fullmatch(r"\s*\d{6}\s*", msg))
        if en_cours.get("ambigu") and code is None:
            m = re.search(r"\b(\d{6})\b", msg)
            if m and m.group(1) in en_cours["ambigu"]:
                o["code"] = m.group(1); o.pop("ambigu", None)
        if "nominal" in en_cours.get("manque", []) and nom is None and not est_code:
            m = re.fullmatch(r"\s*(\d{1,5}(?:[.,]\d+)?)\s*", msg)
            if m:
                o["nominal"] = _nombre(m.group(1)) * 1e6
        if "taux" in en_cours.get("manque", []) and tx is None:
            m = re.fullmatch(r"\s*(\d{1,2}[.,]\d{1,3})\s*%?\s*", msg)
            if m:
                o["taux"] = _nombre(m.group(1)) / 100
        if "contrepartie" in en_cours.get("manque", []) and cp is None and not re.search(r"\d", msg):
            o["contrepartie"] = msg.strip()
    # taux de la ligne depuis les cotations par tenor
    if o.get("cotations") and o.get("code"):
        res = (ref[o["code"]].echeance - aujourdhui).days
        o["taux"], o["mode"] = taux_depuis_tenors(res, o["cotations"])
    elif o.get("cotations") and o.get("code") == "":
        k, v = next(iter(sorted(o["cotations"].items(), key=lambda kv: abs(kv[0] - (o.get("tenor") or kv[0])))))
        o["taux"], o["mode"] = v, f"cote au tenor {k:g} ans"
    manque = [k for k in ("contrepartie", "sens", "code", "nominal") if k not in o]
    if "taux" not in o and "prix" not in o:
        manque.append("taux")
    o["manque"] = manque
    q = []
    if o.get("ambigu") and "code" not in o:
        lib = lambda k: f"{k} ({ref[k].echeance:%d/%m/%Y}, {(ref[k].echeance - aujourdhui).days/365:.1f} ans)"
        q.append("Quelle ligne : " + " ou ".join(lib(k) for k in o["ambigu"][:5]) + (" ? (ou « aucune » pour un interet sur le tenor)" if o.get("tenor") else " ?"))
    for k in manque:
        if k == "code" and o.get("ambigu"):
            continue
        q.append({"contrepartie": "Qui ?", "sens": "Achat ou vente ?", "code": "Quelle ligne (code ou echeance) ?", "nominal": "Quel nominal ?", "taux": "Quel taux (ou prix) ?"}[k])
    o["question"] = " ".join(q)
    o["complet"] = not manque and "code" in o
    return o


# ------------------------------------------------------------------ questions sur les flux
def requete(msg: str, flux: list, ref: dict, aujourdhui: dt.date):
    """Repond aux questions 'qui achete / vend ... ?' et 'resume'. Retourne None si ce n est pas une question."""
    low = msg.lower().strip()
    if not (low.endswith("?") or low.startswith(("qui ", "resume", "résumé", "quoi", "combien"))):
        return None
    jours = 1
    if "semaine" in low: jours = 7
    if "mois" in low: jours = 30
    m = re.search(r"(\d+)\s*(?:j|jours)", low)
    if m: jours = int(m.group(1))
    sens = "Achat" if re.search(r"\bach", low) else ("Vente" if re.search(r"\bvend", low) else None)
    dmin = aujourdhui - dt.timedelta(days=jours - 1)
    sel = []
    for f in flux:
        try:
            d = dt.date.fromisoformat(f["date"])
        except Exception:
            continue
        if d < dmin: continue
        if sens and f.get("sens") != sens: continue
        sel.append(f)
    m_ans = re.search(r"\b(\d{1,2})\s*ans\b", low)
    if m_ans:
        n = int(m_ans.group(1))
        sel = [f for f in sel if (f.get("code") in ref and abs((ref[f["code"]].echeance - aujourdhui).days / 365 - n) <= 1.5)
               or (not f.get("code") and f.get("tenor") and abs(float(f["tenor"]) - n) <= 1.5)]
    else:
        code, cands, _ = lire_ligne(msg, ref, aujourdhui)
        if code:
            sel = [f for f in sel if f.get("code") == code]
        elif cands:
            sel = [f for f in sel if f.get("code") in cands]
    if low.startswith(("resume", "résumé")):
        if not sel:
            return f"Aucun ordre sur {jours} jour(s)."
        ach = [f for f in sel if f["sens"] == "Achat"]; ven = [f for f in sel if f["sens"] == "Vente"]
        tot = lambda L: sum(float(f.get("nominal") or 0) for f in L) / 1e6
        parts = [f"{len(sel)} ordre(s) sur {jours} jour(s)."]
        nomf = lambda f: ref[f['code']].libelle if f.get('code') in ref else (f"interet {float(f['tenor']):g} ans" if f.get('tenor') else f.get('code', '?'))
        if ach: parts.append("Acheteurs : " + ", ".join(f"{f['contrepartie']} {float(f['nominal'] or 0)/1e6:.0f} M {nomf(f)}" for f in ach) + f" (total {tot(ach):.0f} M).")
        if ven: parts.append("Vendeurs : " + ", ".join(f"{f['contrepartie']} {float(f['nominal'] or 0)/1e6:.0f} M {nomf(f)}" for f in ven) + f" (total {tot(ven):.0f} M).")
        parts.append(f"Demande nette : {tot(ach) - tot(ven):+.0f} M.")
        return " ".join(parts)
    if not sel:
        return "Rien de tel sur la periode."
    nomf = lambda f: ref[f['code']].libelle if f.get('code') in ref else (f"interet {float(f['tenor']):g} ans" if f.get('tenor') else f.get('code', '?'))
    lignes = [f"{f['contrepartie']} : {f['sens'].lower()} {float(f.get('nominal') or 0)/1e6:.0f} M {nomf(f)} le {dt.date.fromisoformat(f['date']):%d/%m}" + (f" a {float(f['taux'])*100:.2f} %" if f.get('taux') else "") for f in sel]
    net = sum((1 if f['sens'] == 'Achat' else -1) * float(f.get('nominal') or 0) for f in sel) / 1e6
    return " ; ".join(lignes) + f". Net : {net:+.0f} M."


def phrase_ordre(o: dict, ref: dict) -> str:
    t = ref.get(o.get("code", ""))
    if t:
        lib = f"{o['code']} {t.libelle}"
    elif o.get("code") == "" and o.get("tenor"):
        lib = f"interet sur le {o['tenor']:g} ans (ligne a preciser)"
    else:
        lib = o.get("code", "?")
    s = f"{o.get('contrepartie', '?')} · {o.get('sens', '?').lower()} · {lib} · {o.get('nominal', 0)/1e6:.0f} MMAD"
    if o.get("taux"): s += f" · {o['taux']*100:.3f} %" + (f" ({o['mode']})" if o.get("mode") else "")
    if o.get("prix"): s += f" · prix {o['prix']}"
    if o.get("date"): s += f" · le {o['date']:%d/%m/%Y}"
    return s


# ------------------------------------------------------------------ validite, recherche, matchs
VALIDITE_JOURS = 30


def valable(f: dict, aujourdhui: dt.date) -> bool:
    try:
        d = dt.date.fromisoformat(f["date"])
    except Exception:
        return False
    if (aujourdhui - d).days > VALIDITE_JOURS:
        return False
    return str(f.get("actif", "1")) != "0"


def tenor_de(f: dict, ref: dict, aujourdhui: dt.date):
    """Tenor en annees de l ordre : residuel de la ligne, ou tenor declare."""
    if f.get("code") in ref:
        return (ref[f["code"]].echeance - aujourdhui).days / 365
    try:
        return float(f["tenor"]) if f.get("tenor") else None
    except ValueError:
        return None


def rechercher(flux: list, ref: dict, aujourdhui: dt.date, clients=None, d0=None, d1=None, tenor=None, ligne="", sens=None, valables_seulement=False) -> list:
    out = []
    for f in flux:
        try:
            d = dt.date.fromisoformat(f["date"])
        except Exception:
            continue
        if clients and f.get("contrepartie") not in clients: continue
        if d0 and d < d0: continue
        if d1 and d > d1: continue
        if sens and f.get("sens") != sens: continue
        if ligne:
            l = ligne.strip().lower()
            lib = ref[f["code"]].libelle.lower() if f.get("code") in ref else ""
            ech = ref[f["code"]].echeance.strftime("%d/%m/%Y") if f.get("code") in ref else ""
            if l not in (f.get("code") or "").lower() and l not in lib and l not in ech: continue
        if tenor is not None:
            tn = tenor_de(f, ref, aujourdhui)
            if tn is None or abs(tn - tenor) > (0.3 if tenor < 1.5 else 1.5): continue
        if valables_seulement and not valable(f, aujourdhui): continue
        out.append(f)
    return out


def matchs(flux: list, ref: dict, aujourdhui: dt.date, horizon: int = 7) -> list:
    """Croisements possibles entre achats et ventes valables sur l horizon : meme ligne, ou lignes de meme tenor (±1 an),
    ou interet sur un tenor. Ecart = taux vendeur - taux acheteur en pb (>= 0 : croisable)."""
    dmin = aujourdhui - dt.timedelta(days=horizon)
    cand = [f for f in flux if valable(f, aujourdhui) and dt.date.fromisoformat(f["date"]) >= dmin]
    ach = [f for f in cand if f.get("sens") == "Achat"]; ven = [f for f in cand if f.get("sens") == "Vente"]
    out = []
    for a in ach:
        for v in ven:
            if a.get("contrepartie") == v.get("contrepartie"):
                continue
            ta, tv = tenor_de(a, ref, aujourdhui), tenor_de(v, ref, aujourdhui)
            if a.get("code") and v.get("code") and a["code"] == v["code"]:
                nature = "meme ligne"
            elif ta is not None and tv is not None and abs(ta - tv) <= (0.3 if min(ta, tv) < 1.5 else 1.0):
                nature = "meme tenor"
            else:
                continue
            na, nv = float(a.get("nominal") or 0), float(v.get("nominal") or 0)
            ecart = None
            if a.get("taux") and v.get("taux"):
                ecart = (float(v["taux"]) - float(a["taux"])) * 1e4
            out.append(dict(acheteur=a["contrepartie"], vendeur=v["contrepartie"], nature=nature, ligne_a=a.get("code") or f"{float(a['tenor']):g} ans", ligne_v=v.get("code") or f"{float(v['tenor']):g} ans",
                            nominal=min(na, nv), taux_a=float(a["taux"]) if a.get("taux") else None, taux_v=float(v["taux"]) if v.get("taux") else None, ecart_pb=ecart,
                            date_a=a["date"], date_v=v["date"], verdict="croisable" if (ecart is not None and ecart >= 0) else ("a negocier" if ecart is not None else "taux manquant")))
    out.sort(key=lambda m: (0 if m["verdict"] == "croisable" else 1, -(m["nominal"] or 0)))
    return out
