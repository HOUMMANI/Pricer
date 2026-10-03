"""Utilisateurs : fichier data/utilisateurs.csv, mots de passe haches (PBKDF2), roles admin / trader / lecture."""
from __future__ import annotations
import csv, os, hashlib, secrets, datetime as dt

CHAMPS = ["login", "nom", "role", "sel", "hache", "cree_le", "actif"]
ROLES = ["admin", "trader", "lecture"]


def _hacher(mdp: str, sel: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", mdp.encode("utf-8"), bytes.fromhex(sel), 120_000).hex()


class Utilisateurs:
    def __init__(self, dossier: str):
        self.p = os.path.join(dossier, "utilisateurs.csv")
        if not os.path.exists(self.p):
            self.ecrire([]); self.ajouter("admin", "Administrateur", "admin", "admin")

    def lire(self) -> list:
        with open(self.p, encoding="utf-8") as f:
            return [r for r in csv.DictReader(f, delimiter=";")]

    def ecrire(self, rows: list):
        with open(self.p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CHAMPS, delimiter=";", extrasaction="ignore"); w.writeheader(); w.writerows(rows)

    def ajouter(self, login: str, nom: str, role: str, mdp: str):
        rows = [r for r in self.lire() if r["login"] != login]
        sel = secrets.token_hex(16)
        rows.append(dict(login=login.strip().lower(), nom=nom.strip(), role=role if role in ROLES else "lecture", sel=sel, hache=_hacher(mdp, sel), cree_le=dt.date.today().isoformat(), actif="1"))
        self.ecrire(rows)

    def mot_de_passe(self, login: str, mdp: str):
        rows = self.lire()
        for r in rows:
            if r["login"] == login:
                r["sel"] = secrets.token_hex(16); r["hache"] = _hacher(mdp, r["sel"])
        self.ecrire(rows)

    def desactiver(self, login: str, actif: bool):
        rows = self.lire()
        for r in rows:
            if r["login"] == login:
                r["actif"] = "1" if actif else "0"
        self.ecrire(rows)

    def verifier(self, login: str, mdp: str):
        for r in self.lire():
            if r["login"] == login.strip().lower() and r.get("actif", "1") == "1" and secrets.compare_digest(r["hache"], _hacher(mdp, r["sel"])):
                return dict(login=r["login"], nom=r["nom"], role=r["role"])
        return None
