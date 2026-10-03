"""Resume de 17 h : a lancer par le Planificateur de taches (python resume_17h.py). Envoie par SMTP si configure dans
data/parametres.json ("smtp": {"hote", "port", "utilisateur", "mot_de_passe", "expediteur"}, "resume_destinataires": [...]),
sinon ecrit le resume dans data/resume_<date>.txt."""
import os, sys, json, datetime as dt, smtplib
from email.message import EmailMessage
ICI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, ICI)
from pricer.store import Store
from pricer.referentiel import charger_csv, seulement_bdt
from pricer.pnl import pnl_journalier
from pricer.plus import resume_jour
pct = lambda v, d=3: f"{v*100:.{d}f} %".replace(".", ",")
mnt = lambda v, d=0: f"{v:,.{d}f}".replace(",", " ").replace(".", ",")
store = Store(os.path.join(ICI, "data")); ref = seulement_bdt(charger_csv(os.path.join(ICI, "data", "referentiel.csv"))); par = store.parametres()
auj = dt.date.today(); courbe = store.courbe(auj)
dates = sorted(store.courbes()); pnl = pnl_journalier(store, ref, dates[-2], dates[-1], par.get("methode_defaut", "lignes"), par["taux_financement"]) if len(dates) >= 2 else []
objet, corps = resume_jour(store, ref, auj, courbe, pnl, pct, mnt)
smtp = par.get("smtp"); dest = par.get("resume_destinataires", [])
if smtp and dest:
    m = EmailMessage(); m["Subject"] = objet; m["From"] = smtp.get("expediteur", smtp.get("utilisateur")); m["To"] = ", ".join(dest); m.set_content(corps)
    with smtplib.SMTP(smtp["hote"], int(smtp.get("port", 587))) as s:
        s.starttls()
        if smtp.get("utilisateur"): s.login(smtp["utilisateur"], smtp.get("mot_de_passe", ""))
        s.send_message(m)
    print("envoye a", dest)
else:
    p = os.path.join(ICI, "data", f"resume_{auj.isoformat()}.txt"); open(p, "w", encoding="utf-8").write(objet + "\n\n" + corps); print("ecrit :", p)
