"""Stockage simple et robuste : fichiers CSV (;) dans data/, un par objet. Toutes les dates en ISO."""
from __future__ import annotations
import csv, os, json, datetime as dt
from .courbe import Courbe, Ligne, CLES

CHAMPS = {
    "courbes": ["date"] + CLES + ["source"],
    "lignes": ["date_courbe", "echeance", "taux", "code", "libelle"],
    "ebond": ["date", "heure", "code", "bid", "ask", "taille_bid", "taille_ask", "source"],
    "positions": ["date", "code", "quantite", "spread"],
    "operations": ["id", "date", "date_valeur", "sens", "code", "quantite", "nominal", "prix_plein", "taux", "contrepartie", "client", "fonds", "parent_id", "intermediation_id", "canal", "nature", "commentaire", "saisie_le"],
    "tiers": ["nom", "type", "parent", "depositaire"],
    "contacts": ["contrepartie", "nom", "email", "role"],
    "flux": ["id", "date", "heure", "auteur", "contrepartie", "sens", "code", "tenor", "nominal", "taux", "prix", "mode", "cotations", "texte", "actif"],
}
PARAMETRES_DEFAUT = {
    "taux_financement": 0.0275, "methode_defaut": "lignes", "regle_ebond": "lignes",
    "limites_nominal": [["Nominal global", 0, 6000000000], ["Nominal >= 1 an", 1, 5700000000], ["Nominal >= 5 ans", 5, 3200000000], ["Nominal >= 10 ans", 10, 500000000], ["Nominal >= 15 ans", 15, 300000000]],
    "limites_sensi": [["Sensi globale", 0, 2500000], ["Sensi >= 1 an", 1, 2300000], ["Sensi >= 3 ans", 3, 2200000], ["Sensi >= 5 ans", 5, 1600000], ["Sensi >= 10 ans", 10, 582000]],
}


class Store:
    def __init__(self, dossier: str):
        self.d = dossier
        os.makedirs(dossier, exist_ok=True)

    # ------------------------------------------------------------ bas niveau
    def _chemin(self, nom):
        return os.path.join(self.d, nom + ".csv")

    def lire(self, nom) -> list:
        p = self._chemin(nom)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [r for r in csv.DictReader(f, delimiter=";")]

    def ecrire(self, nom, rows: list):
        with open(self._chemin(nom), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CHAMPS[nom], delimiter=";", extrasaction="ignore")
            w.writeheader(); w.writerows(rows)

    def ajouter(self, nom, rows: list):
        self.ecrire(nom, self.lire(nom) + rows)

    # ------------------------------------------------------------ parametres
    def parametres(self) -> dict:
        p = os.path.join(self.d, "parametres.json")
        base = dict(PARAMETRES_DEFAUT)
        if os.path.exists(p):
            try:
                base.update(json.load(open(p, encoding="utf-8")))
            except Exception:
                pass
        return base

    def enregistrer_parametres(self, par: dict):
        json.dump(par, open(os.path.join(self.d, "parametres.json"), "w", encoding="utf-8"), indent=1)

    # ------------------------------------------------------------ courbes
    def courbes(self) -> dict:
        out = {}
        for r in self.lire("courbes"):
            try:
                out[dt.date.fromisoformat(r["date"])] = ([float(r[k]) for k in CLES], r.get("source", ""))
            except Exception:
                continue
        return out

    def lignes_publiees(self) -> dict:
        out = {}
        for r in self.lire("lignes"):
            try:
                out.setdefault(dt.date.fromisoformat(r["date_courbe"]), []).append(Ligne(dt.date.fromisoformat(r["echeance"]), float(r["taux"]), r.get("code") or "", r.get("libelle") or ""))
            except Exception:
                continue
        for d in out:
            out[d].sort(key=lambda l: l.echeance)
        return out

    def courbe(self, d: dt.date) -> Courbe | None:
        """Courbe publiee a la date d, sinon la derniere publiee avant (veille rapportee)."""
        cs = self.courbes()
        dates = sorted(x for x in cs if x <= d)
        if not dates:
            return None
        base = dates[-1]
        taux, src = cs[base]
        return Courbe(base, taux, self.lignes_publiees().get(base, []), src if base == d else f"veille rapportee : courbe du {base:%d/%m/%Y}")

    def enregistrer_courbe(self, c: Courbe):
        rows = [r for r in self.lire("courbes") if r["date"] != c.date.isoformat()]
        rows.append({"date": c.date.isoformat(), **{k: f"{t:.6f}" for k, t in zip(CLES, c.taux)}, "source": c.source})
        rows.sort(key=lambda r: r["date"])
        self.ecrire("courbes", rows)
        if c.lignes:
            lg = [r for r in self.lire("lignes") if r["date_courbe"] != c.date.isoformat()]
            lg += [{"date_courbe": c.date.isoformat(), "echeance": l.echeance.isoformat(), "taux": f"{l.taux:.6f}", "code": l.code, "libelle": l.libelle} for l in c.lignes]
            self.ecrire("lignes", lg)

    # ------------------------------------------------------------ eBond
    def ebond(self, d: dt.date) -> list:
        out = []
        for r in self.lire("ebond"):
            if r["date"] == d.isoformat():
                out.append(r)
        return out

    def enregistrer_ebond(self, d: dt.date, rows: list, remplacer=True):
        base = [r for r in self.lire("ebond") if not (remplacer and r["date"] == d.isoformat())]
        self.ecrire("ebond", base + [{**r, "date": d.isoformat()} for r in rows])

    # ------------------------------------------------------------ positions et operations
    def photos(self) -> dict:
        out = {}
        for r in self.lire("positions"):
            try:
                out.setdefault(dt.date.fromisoformat(r["date"]), []).append(r)
            except Exception:
                continue
        return out

    def enregistrer_photo(self, d: dt.date, rows: list):
        base = [r for r in self.lire("positions") if r["date"] != d.isoformat()]
        self.ecrire("positions", base + [{"date": d.isoformat(), "code": str(r["code"]).strip(), "quantite": r["quantite"], "spread": r.get("spread", "") or ""} for r in rows])

    def operations(self) -> list:
        return self.lire("operations")

    def enregistrer_operations(self, rows: list):
        self.ecrire("operations", rows)

    def flux(self) -> list:
        return self.lire("flux")

    def enregistrer_flux(self, rows: list):
        self.ecrire("flux", rows)

    def tiers(self) -> list:
        return self.lire("tiers")

    def enregistrer_tiers(self, rows: list):
        self.ecrire("tiers", rows)

    def contacts(self) -> list:
        return self.lire("contacts")

    def enregistrer_contacts(self, rows: list):
        self.ecrire("contacts", rows)

    def positions_a(self, d: dt.date, ref: dict, base: str = "operation") -> tuple:
        """Positions a la date d : derniere photo <= d, plus les operations enregistrees apres la photo et jusqu a d.
        base : 'operation' (date d operation) ou 'valeur' (date valeur). Les ventilations (parent_id) ne comptent pas :
        c est l operation en bloc qui porte la position. Retourne (dict code -> (quantite, spread), date de la photo)."""
        ph = self.photos()
        dates = sorted(x for x in ph if x <= d)
        pos = {}
        photo = None
        if dates:
            photo = dates[-1]
            for r in ph[photo]:
                try:
                    q = float(str(r["quantite"]).replace(",", "."))
                except ValueError:
                    continue
                if q:
                    pos[str(r["code"]).strip()] = [q, r.get("spread", "") or ""]
        for o in self.operations():
            if o.get("parent_id"):
                continue
            try:
                od = dt.date.fromisoformat(o.get("date_valeur") or o["date"]) if base == "valeur" else dt.date.fromisoformat(o["date"])
            except Exception:
                continue
            if (photo is None or od > photo) and od <= d:
                code = str(o["code"]).strip(); t = ref.get(code)
                q = float(o["quantite"] or 0) if o.get("quantite") else (float(o["nominal"]) / t.nominal if (t and o.get("nominal")) else 0)
                if not q:
                    continue
                signe = 1 if o["sens"].lower().startswith("a") else -1
                cur = pos.get(code, [0.0, ""])
                cur[0] += signe * q
                if abs(cur[0]) < 1e-9:
                    pos.pop(code, None)
                else:
                    pos[code] = cur
        return pos, photo
