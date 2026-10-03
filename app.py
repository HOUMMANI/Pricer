"""Pricer Valorisation Maroc - version 2 (Streamlit)."""
from __future__ import annotations
import os, io, datetime as dt, urllib.parse
import pandas as pd
import streamlit as st
import altair as alt

from pricer.referentiel import charger_csv, charger_excel, seulement_bdt
from pricer.store import Store
from pricer.courbe import Courbe, Ligne, TENORS, CLES
from pricer.bdt import caracteristiques, prix_plein, coupon_couru, taux_depuis_prix, valoriser
from pricer.portefeuille import valoriser_portefeuille, agregats, limites, tranches
from pricer.intraday import courbe_du_jour, REGLES
from pricer.pnl import pnl_journalier
from pricer.swap import simuler
from pricer import bkam
from pricer.acces import Utilisateurs
from pricer.plus import radar, placer, courbe_des_ordres, memoire, resume_jour, alertes
from pricer.ticket import ticket_pdf
from pricer.qualif import qualifier, resume as resume_qualif, NATURES, CANAUX
from pricer.simulateur import deformer, appliquer_operations, evaluer, krd, scenarios as scenarios_sim, var_historique, pnl_horizon, couverture
from pricer.feuille import CourbeFeuille, chocs, trend
from pricer.carnet import comprendre, requete, phrase_ordre, rechercher, matchs, valable, tenor_de

ICI = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(ICI, "data")
BLEU, ROUGE, VERT, GRIS = "#0071CE", "#C9285A", "#1E8E4A", "#5E6675"
store = Store(DATA)
usagers = Utilisateurs(DATA)

st.set_page_config(page_title="Pricer Valorisation Maroc", page_icon="📈", layout="wide")
st.markdown(f"""<style>
h1,h2,h3{{color:{BLEU}}} div[data-testid="stMetricValue"]{{color:{BLEU};font-size:1.45rem;font-family:Georgia,serif}} .stMetric label{{color:{GRIS};letter-spacing:.08em;font-size:.72rem;text-transform:uppercase}}
.bandeau{{background:#003D70;color:#fff;padding:10px 22px 9px;border-bottom:3px solid {ROUGE};margin:-1rem -1rem 14px -1rem;display:flex;gap:34px;align-items:flex-end;flex-wrap:wrap}}
.bandeau .t{{font-size:.95rem;font-weight:700;letter-spacing:.25em}} .bandeau .k{{font-size:.6rem;letter-spacing:.2em;color:#9CC6F0}} .bandeau .v{{font-size:.95rem;font-weight:700}} .bandeau .w{{color:#FFC857}} .bandeau .r{{color:#FF8FA8}}
.zone{{font-size:.68rem;letter-spacing:.22em;font-weight:700;color:{BLEU};margin:2px 0 6px}} .zone small{{display:block;letter-spacing:0;font-weight:400;color:{GRIS};text-transform:none;font-size:.78rem}}
.note{{background:#F0F7FC;border-left:3px solid {ROUGE};padding:6px 12px;font-size:.85rem;color:#1B2333;margin:6px 0 12px}}
.carte{{border:1px solid #E1E9F0;border-radius:8px;padding:8px 12px;margin-bottom:8px;background:#fff}} .carte.on{{border-color:{ROUGE};background:#FCEFF3}}
.carte .n{{font-size:.72rem;letter-spacing:.15em;font-weight:700;color:#1B2333}} .carte.on .n{{color:{ROUGE}}} .carte .g{{font-family:Georgia,serif;font-size:1.35rem;color:{BLEU};float:right}} .carte.on .g{{color:{ROUGE}}} .carte .d{{font-size:.76rem;color:{GRIS}}}
.big .k{{font-size:.62rem;letter-spacing:.18em;color:{GRIS}}} .big .v{{font-family:Georgia,serif;font-size:1.6rem;color:{BLEU}}} .big .v.r{{color:{ROUGE}}}
section[data-testid="stSidebar"] div[role="radiogroup"] label{{border:1px solid #E1E9F0;border-radius:8px;padding:9px 12px;margin:3px 0;background:#fff;width:100%}}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){{background:{ROUGE};border-color:{ROUGE}}} section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p{{color:#fff;font-weight:700}}
section[data-testid="stSidebar"] div[role="radiogroup"] label p{{font-size:.85rem;letter-spacing:.12em;font-weight:600}}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------- identification
if "user" not in st.session_state:
    st.markdown("<div style='max-width:380px;margin:80px auto 0'><div style='background:#003D70;color:#fff;padding:14px 18px;border-bottom:3px solid #C9285A;font-weight:700;letter-spacing:.25em'>ATELIERS TAUX</div></div>", unsafe_allow_html=True)
    _, c, _ = st.columns([1, 1.1, 1])
    with c:
        with st.form("connexion"):
            lg = st.text_input("Identifiant"); mdp = st.text_input("Mot de passe", type="password")
            if st.form_submit_button("Entrer", type="primary"):
                u = usagers.verifier(lg, mdp)
                if u:
                    st.session_state.user = u; st.session_state.auteur = u["nom"]; st.rerun()
                else:
                    st.error("Identifiant ou mot de passe incorrect.")
    st.stop()
user = st.session_state.user
peut_ecrire = True            # tous les utilisateurs : utilisation complete
est_admin = True


# ----------------------------------------------------------------- utilitaires
def pct(v, d=3):
    return "" if v is None else f"{v*100:.{d}f} %".replace(".", ",")


def mnt(v, d=0):
    return "" if v is None else f"{v:,.{d}f}".replace(",", " ").replace(".", ",")


def num(v, d=4):
    return "" if v is None else f"{v:.{d}f}".replace(".", ",")


def fdate(d):
    return d.strftime("%d/%m/%Y") if d else ""


def excel_bytes(frames: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nom, df in frames.items():
            df.to_excel(w, sheet_name=nom[:31], index=False)
    return buf.getvalue()


def rouge_vert(v):
    if isinstance(v, (int, float)):
        return f"color:{ROUGE}" if v < 0 else f"color:{VERT}"
    return ""


@st.cache_data
def _ref_defaut():
    return seulement_bdt(charger_csv(os.path.join(DATA, "referentiel.csv")))


if "ref" not in st.session_state:
    st.session_state.ref = _ref_defaut()
ref: dict = st.session_state.ref
par = store.parametres()
courbes_dispo = store.courbes()

# ----------------------------------------------------------------- rail des ateliers et bandeau
st.sidebar.markdown("<div style='font-size:.65rem;letter-spacing:.3em;color:#5E6675;margin-bottom:6px'>ATELIERS</div>", unsafe_allow_html=True)
ATELIERS = ["COTER", "PRIX ↔ TAUX", "OPÉRER", "QUALIFIER", "PORTEFEUILLE", "SIMULATEUR", "P&L", "SWAPPER", "CARNET", "COURBE", "RÉSUMÉ", "CONTACTS", "RÉFÉRENTIEL", "PARAMÈTRES"]
if "atelier" not in st.session_state:
    st.session_state.atelier = "COTER"
if "aller" in st.session_state:
    st.session_state.atelier = st.session_state.pop("aller")


def _prefere(cands):
    """Parmi plusieurs titres : d abord les BDT, puis le code le plus recent."""
    return sorted(cands, key=lambda k: (0 if "BDT" in ref[k].libelle.upper() else 1, -int(k) if k.isdigit() else 0))[0]


def _commande():
    q = st.session_state.get("cmd", "").strip()
    if not q:
        return
    code = None
    if q in ref:
        code = q
    else:
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d%m%Y", "%d%m%y"):
            try:
                e = dt.datetime.strptime(q, fmt).date()
                cands = [k for k in ref if ref[k].echeance == e]
                if cands:
                    code = _prefere(cands)
                break
            except ValueError:
                continue
        if code is None:
            cands = [k for k in ref if q.lower() in ref[k].libelle.lower() or k.startswith(q)]
            if len(cands) >= 1:
                code = _prefere(cands)
    if code:
        st.session_state.dernier_titre = code
        for k in ("cot", "cot_ech", "cot_multi", "op", "op_ech", "op_multi"):
            st.session_state.pop(k, None)
        st.session_state.atelier = "COTER"
    st.session_state.cmd = ""


st.sidebar.markdown(f"<div style='font-size:.8rem;color:#1B2333'><b>{user['nom']}</b></div>", unsafe_allow_html=True)
if st.sidebar.button("Quitter"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()
st.sidebar.text_input("Commande", key="cmd", placeholder="code ou échéance, puis Entrée", on_change=_commande, label_visibility="collapsed")
page = st.sidebar.radio("Ateliers", ATELIERS, key="atelier", label_visibility="collapsed")
st.sidebar.markdown("---")
date_val = st.sidebar.date_input("Date", value=max(courbes_dispo) if courbes_dispo else dt.date.today(), format="DD/MM/YYYY")
methode = st.sidebar.selectbox("Lecture", ["lignes", "tenors"], index=0 if par.get("methode_defaut", "lignes") == "lignes" else 1,
                               format_func=lambda m: "Taux de la ligne" if m == "lignes" else "Tenors")
source_courbe = st.sidebar.selectbox("Courbe", ["Courbe de la date", "Courbe du jour"], index=0)
base_pos = st.sidebar.selectbox("Positions en", ["operation", "valeur"], index=0, format_func=lambda b: "date d'operation" if b == "operation" else "date valeur")


def courbe_active(d: dt.date) -> Courbe | None:
    c = store.courbe(d)
    if c is None:
        return None
    if source_courbe.startswith("Courbe du jour"):
        q = [dict(code=r["code"], bid=r["bid"], ask=r["ask"]) for r in store.ebond(d)]
        return courbe_du_jour(c, q, ref, d, par.get("regle_ebond", "lignes"))
    return c


courbe = courbe_active(date_val)


@st.cache_data(show_spinner=False)
def _resume_cache(d_iso, taux, src, sig_pos, meth, lim_n, lim_s):
    return _resume_calc(dt.date.fromisoformat(d_iso))


def _resume_calc(d):
    pos, _ = store.positions_a(d, ref, base_pos)
    vm = pv = 0.0; alerte = ""
    if pos and courbe:
        lg = valoriser_portefeuille([(k, v[0], v[1]) for k, v in pos.items()], ref, courbe, date_val, methode)
        ag = agregats(lg); vm, pv = ag["valeur_marche"], ag["pvbp"]
        g = {"nominal": [tuple(x) for x in par["limites_nominal"]], "sensi": [tuple(x) for x in par["limites_sensi"]]}
        st_ = [x["statut"] for x in limites(lg, g)]
        nd, nv = st_.count("DEPASSEMENT"), st_.count("Vigilance")
        alerte = (f"<span class='r'>{nd} depassement(s)</span>" if nd else "") + (f" <span class='w'>{nv} en vigilance</span>" if nv else "") or "toutes OK"
    return vm, pv, alerte


_sig = str(sorted((k, v[0]) for k, v in store.positions_a(date_val, ref, base_pos)[0].items()))
vm_b, pv_b, al_b = _resume_cache(date_val.isoformat(), tuple(courbe.taux) if courbe else (), courbe.source if courbe else "", _sig, methode, str(par["limites_nominal"]), str(par["limites_sensi"]))


def _alertes():
    pos, _ = store.positions_a(date_val, ref, base_pos); rows = []
    if pos and courbe:
        g = {"nominal": [tuple(x) for x in par["limites_nominal"]], "sensi": [tuple(x) for x in par["limites_sensi"]]}
        rows = limites(valoriser_portefeuille([(k, v[0], v[1]) for k, v in pos.items()], ref, courbe, date_val, methode), g)
    return alertes(store, ref, dt.date.today(), rows, store.ebond(date_val))


liste_alertes = _alertes()
if liste_alertes:
    st.sidebar.markdown(f"<div style='background:#FCEFF3;border-left:3px solid #C9285A;padding:4px 8px;font-size:.8rem;margin:4px 0'>⚑ <b>{len(liste_alertes)}</b> alerte(s)</div>", unsafe_allow_html=True)
st.markdown(f"""<div class='bandeau'><div><div class='k'>CRÉDIT DU MAROC · SALLE DES MARCHÉS</div><div class='t'>ATELIERS TAUX</div></div>
<div><div class='k'>DATE</div><div class='v'>{date_val:%d/%m/%Y}</div></div>
<div><div class='k'>COURBE</div><div class='v'>{(courbe.source if courbe else 'aucune')[:46]}</div></div>
<div><div class='k'>PORTEFEUILLE</div><div class='v'>{mnt(vm_b/1e6,1)} MMAD · PVBP {mnt(pv_b)} MAD/pb</div></div>
<div><div class='k'>LIMITES</div><div class='v'>{al_b or '—'}</div></div></div>""", unsafe_allow_html=True)
if liste_alertes:
    with st.expander(f"⚑ {len(liste_alertes)} alerte(s)"):
        for col, txt in liste_alertes:
            st.markdown(f"<span style='color:{ {'rouge': ROUGE, 'orange': '#E5541E', 'vert': VERT}[col] }'>●</span> {txt}", unsafe_allow_html=True)
if courbe:
    _prev = sorted(x for x in courbes_dispo if x < courbe.date)
    _tp = courbes_dispo[_prev[-1]][0] if _prev else None
    _items = []
    for k, (nom, j, _) in enumerate(TENORS):
        v = courbe.taux[k]
        if _tp:
            dv = (v - _tp[k]) * 1e4
            fl = "▲" if dv > 0.05 else ("▼" if dv < -0.05 else "■"); col = "#FF8FA8" if dv > 0.05 else ("#7CE0A0" if dv < -0.05 else "#C3DEF4")
            _items.append(f"<span class='tk'><b>{nom}</b> {pct(v)} <span style='color:{col}'>{fl} {dv:+.1f} pb</span></span>")
        else:
            _items.append(f"<span class='tk'><b>{nom}</b> {pct(v)}</span>")
    _txt = "".join(_items) + f"<span class='tk' style='color:#9CC6F0'>courbe du {courbe.date:%d/%m/%Y}" + (f" vs {_prev[-1]:%d/%m/%Y}" if _prev else "") + "</span>"
    st.markdown(f"""<style>.ticker{{background:#00264A;color:#fff;overflow:hidden;white-space:nowrap;margin:-14px -1rem 12px -1rem;padding:5px 0;font-size:.8rem;border-bottom:1px solid #0071CE}}
.ticker .track{{display:inline-block;animation:defile 40s linear infinite}} .ticker:hover .track{{animation-play-state:paused}} .tk{{margin:0 22px}}
@keyframes defile{{0%{{transform:translateX(0)}}100%{{transform:translateX(-50%)}}}}</style>
<div class='ticker'><div class='track'>{_txt}{_txt}</div></div>""", unsafe_allow_html=True)
else:
    st.warning("Aucune courbe.")


def choisir_titre(cle, d=None):
    """Choix d un titre par son code, ou par sa date d echeance."""
    d = d or date_val
    codes = [k for k in sorted(ref, key=lambda k: (ref[k].echeance, k)) if ref[k].echeance > d]
    mode = st.radio("Choisir par", ["Code", "Échéance"], horizontal=True, key=cle + "_mode", label_visibility="collapsed")
    pref = st.session_state.get("dernier_titre") or "201898"
    if mode == "Code":
        opt = [f"{k} - {ref[k].libelle}" for k in codes]
        idx = next((i for i, o in enumerate(opt) if o.startswith(pref + " ")), 0)
        s = st.selectbox("Titre (code - libelle)", opt, index=idx, key=cle)
        return ref[s.split(" - ")[0]] if s else None
    echs = sorted({ref[k].echeance for k in codes})
    pref_e = ref[pref].echeance if pref in ref else echs[0]
    e = st.selectbox("Échéance", echs, index=echs.index(pref_e) if pref_e in echs else 0, format_func=lambda x: x.strftime("%d/%m/%Y"), key=cle + "_ech")
    cands = sorted([k for k in codes if ref[k].echeance == e], key=lambda k: (0 if "BDT" in ref[k].libelle.upper() else 1, k))
    if len(cands) == 1:
        st.caption(f"{cands[0]} - {ref[cands[0]].libelle}")
        return ref[cands[0]]
    s = st.selectbox("Plusieurs titres a cette echeance", [f"{k} - {ref[k].libelle}" for k in cands], key=cle + "_multi")
    return ref[s.split(" - ")[0]] if s else None


def positions_df(d: dt.date):
    pos, base = store.positions_a(d, ref, base_pos)
    return pd.DataFrame([dict(code=k, quantite=v[0], spread=v[1]) for k, v in pos.items()]), base


# ================================================================= 1 - COURBE
def page_courbe():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>COURBE</span>&nbsp;&nbsp;<span style='color:#5E6675'></span>", unsafe_allow_html=True)
    g, dr = st.columns([1, 1.3])
    with g:
        st.subheader("Alimenter")
        src = st.radio("Source", ["Site BKAM", "Fichier BKAM", "Saisie"], label_visibility="collapsed")
        if src == "Site BKAM":
            dd = st.date_input("Date demandee", value=date_val, format="DD/MM/YYYY", key="dbkam")
            if st.button("Lire BKAM", type="primary", disabled=not peut_ecrire):
                try:
                    with st.spinner("Lecture du site BKAM..."):
                        c = bkam.courbe_bkam(dd, ref)
                    store.enregistrer_courbe(c); st.success(f"Courbe du {fdate(c.date)} enregistree : {len(c.lignes)} lignes. {c.source}"); st.rerun()
                except Exception as e:
                    st.error(f"Lecture impossible : {e}")
        elif src == "Fichier BKAM":
            up = st.file_uploader("Fichier", type=["csv", "txt", "html", "htm"])
            if up is not None and st.button("Lire le fichier", type="primary", disabled=not peut_ecrire):
                try:
                    c = bkam.courbe_depuis_contenu(up.getvalue().decode("utf-8", errors="ignore"), ref)
                    store.enregistrer_courbe(c); st.success(f"Courbe du {fdate(c.date)} enregistree : {len(c.lignes)} lignes."); st.rerun()
                except Exception as e:
                    st.error(f"Fichier illisible : {e}")
        else:
            base = store.courbe(date_val)
            vals = []; cols = st.columns(3)
            for k, (nom, j, conv) in enumerate(TENORS):
                vals.append(cols[k % 3].number_input(f"{nom}", value=float((base.taux[k] if base else 0.02) * 100), step=0.005, format="%.3f", key=f"man{k}", help=conv) / 100)
            if st.button("Enregistrer", type="primary", disabled=not peut_ecrire):
                store.enregistrer_courbe(Courbe(date_val, vals, [], "saisie manuelle")); st.success("Courbe enregistree."); st.rerun()
        st.subheader("eBond")
        eb = pd.DataFrame(store.ebond(date_val)) if store.ebond(date_val) else pd.DataFrame(columns=["code", "bid", "ask", "taille_bid", "taille_ask"])
        eb = st.data_editor(eb[["code", "bid", "ask", "taille_bid", "taille_ask"]] if len(eb.columns) >= 5 else eb, num_rows="dynamic", width="stretch", key="ebedit",
                            column_config={"code": st.column_config.TextColumn("Code"), "bid": st.column_config.NumberColumn("Bid (taux %)", format="%.3f"), "ask": st.column_config.NumberColumn("Ask (taux %)", format="%.3f"),
                                           "taille_bid": st.column_config.NumberColumn("Taille bid (MMAD)"), "taille_ask": st.column_config.NumberColumn("Taille ask (MMAD)")})
        if st.button("Enregistrer eBond", disabled=not peut_ecrire):
            rows = []
            for _, r in eb.iterrows():
                if str(r.get("code", "")).strip() in ("", "nan", "None"):
                    continue
                conv = lambda v: "" if pd.isna(v) or v in ("", None) else (float(v) / 100 if float(v) > 1 else float(v))
                rows.append(dict(heure=dt.datetime.now().strftime("%H:%M"), code=str(r["code"]).strip(), bid=conv(r.get("bid")), ask=conv(r.get("ask")), taille_bid=r.get("taille_bid", ""), taille_ask=r.get("taille_ask", ""), source="eBond"))
            store.enregistrer_ebond(date_val, rows); st.success(f"{len(rows)} cotations enregistrees pour le {fdate(date_val)}."); st.rerun()
    with dr:
        if courbe:
            st.subheader(f"Courbe · {courbe.source}")
            df = pd.DataFrame(courbe.tableau())
            st.dataframe(pd.DataFrame({"Tenor": df["tenor"], "Jours": df["jours"], "Convention": df["convention"], "Publie": df["publie"].map(pct), "Actuariel": df["actuariel"].map(pct)}), hide_index=True, width="stretch")
            base = store.courbe(date_val)
            ch = pd.DataFrame({"Maturite (ans)": [j / 365 for _, j, _ in TENORS], "Courbe retenue (%)": [a * 100 for a in courbe.actuariels()]})
            if base and source_courbe.startswith("Courbe du jour"):
                ch["Courbe BKAM de base (%)"] = [a * 100 for a in base.actuariels()]
            st.line_chart(ch.set_index("Maturite (ans)"))
            if courbe.lignes:
                with st.expander(f"Lignes ({len(courbe.lignes)})"):
                    st.dataframe(pd.DataFrame([dict(Echeance=fdate(l.echeance), Maturite=round((l.echeance - courbe.date).days / 365, 2), Taux=pct(l.taux), Code=l.code, Libelle=l.libelle) for l in courbe.lignes]), hide_index=True, width="stretch")
    st.subheader("Courbe des ordres")
    co = courbe_des_ordres(store.flux(), ref, dt.date.today(), courbe, store.ebond(date_val))
    if any(x["implicite"] is not None for x in co):
        st.dataframe(pd.DataFrame([dict(Tenor=x["tenor"], Acheteurs=pct(x["acheteurs"]) if x["acheteurs"] else "", Vendeurs=pct(x["vendeurs"]) if x["vendeurs"] else "", Ordres=f"{x['nb_achats']} / {x['nb_ventes']}", Implicite=pct(x["implicite"]) if x["implicite"] else "", BAM=pct(x["bam"]) if x["bam"] else "", eBond=pct(x["ebond"]) if x["ebond"] else "", **{"Ordres - BAM (pb)": round(x["ecart_bam_pb"], 1) if x["ecart_bam_pb"] is not None else None}) for x in co]), hide_index=True, width="stretch")
        ch = pd.DataFrame({"Maturite": [j / 365 for _, j, _ in TENORS], "BAM (%)": [x["bam"] * 100 if x["bam"] else None for x in co], "Ordres (%)": [x["implicite"] * 100 if x["implicite"] else None for x in co], "eBond (%)": [x["ebond"] * 100 if x["ebond"] else None for x in co]}).set_index("Maturite")
        st.line_chart(ch)
    else:
        st.caption("Aucun ordre valable avec taux.")
    st.subheader("Historique")
    if courbes_dispo:
        dh = pd.DataFrame([dict(Date=fdate(d), **{TENORS[k][0]: pct(v[0][k]) for k in range(9)}, Source=v[1]) for d, v in sorted(courbes_dispo.items(), reverse=True)])
        st.dataframe(dh, hide_index=True, width="stretch", height=min(400, 40 + 35 * len(dh)))
        dates = sorted(courbes_dispo); a, b = st.columns(2)
        d0 = a.selectbox("Du", dates, index=0, format_func=fdate); d1 = b.selectbox("Au", dates, index=len(dates) - 1, format_func=fdate)
        st.dataframe(pd.DataFrame([{"Tenor": TENORS[k][0], "Debut": pct(courbes_dispo[d0][0][k]), "Fin": pct(courbes_dispo[d1][0][k]), "Variation (pb)": round((courbes_dispo[d1][0][k] - courbes_dispo[d0][0][k]) * 1e4, 1)} for k in range(9)]), hide_index=True, width="stretch")
        st.download_button("Exporter (CSV)", open(os.path.join(DATA, "courbes.csv"), "rb").read(), "courbes.csv", "text/csv")


# ================================================================= ATELIER COTER (feuille Valorisation)
def zone(t, sub=""):
    st.markdown(f"<div class='zone'>{t}<small>{sub}</small></div>", unsafe_allow_html=True)


def carte(nom, detail, valeur, on=False):
    st.markdown(f"<div class='carte{' on' if on else ''}'><span class='g'>{valeur}</span><div class='n'>{nom}</div><div class='d'>{detail}</div></div>", unsafe_allow_html=True)


def big(lab, val, rouge=False):
    st.markdown(f"<div class='big'><div class='k'>{lab}</div><div class='v{' r' if rouge else ''}'>{val}</div></div>", unsafe_allow_html=True)


def atelier_coter():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>COTER</span>&nbsp;&nbsp;<span style='color:#5E6675'></span>", unsafe_allow_html=True)
    z1, z2, z3 = st.columns([1, 1.15, 1.05], gap="medium")
    # ---------------- 1 contexte
    with z1:
        zone("1 · CONTEXTE")
        d = st.date_input("Date de calcul", value=date_val, format="DD/MM/YYYY", key="dcot")
        c = courbe_active(d)
        q0 = st.session_state.get("recherche", "")
        t = choisir_titre("cot", d)
        if not t:
            return
        qte = st.number_input("Quantite (titres)", value=100, min_value=1, step=10)
        clients = sorted({x["contrepartie"] for x in store.contacts() if x.get("contrepartie")} | {f["contrepartie"] for f in store.flux() if f.get("contrepartie")})
        client = st.selectbox("Client", [""] + clients, key="cot_client")
        spread = 0.0
        car = caracteristiques(t, d)
        st.caption(f"{fdate(t.echeance)} · {pct(t.taux_facial, 2)} · {car.residuel} j · {car.regime.split(' - ')[0]}")
        with st.expander("Fiche"):
            st.table(pd.DataFrame({"Fiche": ["ISIN", "Jouissance", "Echeance", "Coupon", "Nominal unitaire", "Maturite initiale", "Residuel", "Premier coupon", "Prochain coupon", "Coupons restants", "Regime"],
                                   "Valeur": [t.isin, fdate(t.jouissance), fdate(t.echeance), pct(t.taux_facial, 2), mnt(t.nominal), f"{car.duree_initiale} j", f"{car.residuel} j · {car.residuel/365:.2f} ans", fdate(car.premier_coupon), fdate(car.prochain_coupon), str(car.n), car.regime]}).set_index("Fiche"))
        pos, _ = store.positions_a(d, ref, base_pos)
        if t.code in pos:
            st.markdown(f"<div class='note'><b>Position</b> : {mnt(pos[t.code][0] * t.nominal)} MAD · {pos[t.code][0]:.0f} titres</div>", unsafe_allow_html=True)
        if c:
            st.caption(f"Courbe : {c.source}")
    if not c:
        with z2:
            st.warning("Aucune courbe a cette date."); return
    residuel = (t.echeance - d).days
    # ---------------- 2 travail
    with z2:
        zone("2 · TRAVAIL")
        ebond_force = st.session_state.setdefault("ebond_force", {})
        with st.expander("Courbe de la feuille", expanded=False):
            hb = st.radio("Hors bornes", ["bam", "extrapolation"], horizontal=True, format_func=lambda x: "Tenor BAM" if x == "bam" else "Extrapolation")
            cf0 = CourbeFeuille(c, ref, d, ebond_force, hb)
            dfl = pd.DataFrame([dict(code=l.code, libelle=l.libelle, echeance=fdate(l.echeance), jours=l.jours, taux_bam=(l.taux_bam or 0) * 100, taux_force=(l.taux_ebond * 100 if l.taux_ebond is not None else None)) for l in cf0.lignes])
            ed = st.data_editor(dfl, hide_index=True, width="stretch", key="edlignes", disabled=["code", "libelle", "echeance", "jours", "taux_bam"],
                                column_config={"taux_bam": st.column_config.NumberColumn("Taux BAM (%)", format="%.3f"), "taux_force": st.column_config.NumberColumn("Taux force (%)", format="%.3f")})
            nouveau = {str(r["code"]): float(r["taux_force"]) / 100 for _, r in ed.iterrows() if pd.notna(r.get("taux_force")) and r.get("taux_force") not in ("", None)}
            if nouveau != ebond_force:
                st.session_state.ebond_force = nouveau; st.rerun()
            cf = CourbeFeuille(c, ref, d, ebond_force, hb)
            ten = cf.tableau_tenors()
            tdf = pd.DataFrame([dict(Tenor=x["tenor"], Jours=x["jours"], Convention=x["convention"], **{"Calcule": pct(x["calcule"]), "Retenu": x["retenu"] * 100, "Ecart (pb)": round(x["ecart_pb"], 1) if x["ecart_pb"] is not None else None}) for x in ten])
            edt = st.data_editor(tdf, hide_index=True, width="stretch", key="edtenors", disabled=["Tenor", "Jours", "Convention", "Calcule", "Ecart (pb)"], column_config={"Retenu": st.column_config.NumberColumn("Retenu (%)", format="%.3f")})
            cf.tenors_retenus = [float(v) / 100 for v in edt["Retenu"]]
        if "cf" not in dir() or cf is None:
            cf = CourbeFeuille(c, ref, d, ebond_force, "bam")
        # lecture 1
        l1 = cf.lecture_tenors(residuel)
        st.markdown("**Lecture 1 · Tenors**")
        a, b = st.columns(2)
        f1b = a.number_input(f"{l1['borne_basse']} ({l1['jours_bas']} j) — courbe {pct(l1['taux_bas'])}", value=None, placeholder="forcer", step=0.001, format="%.3f", key="f1b")
        f1h = b.number_input(f"{l1['borne_haute']} ({l1['jours_haut']} j) — courbe {pct(l1['taux_haut'])}", value=None, placeholder="forcer", step=0.001, format="%.3f", key="f1h")
        l1 = cf.lecture_tenors(residuel, f1b / 100 if f1b is not None else None, f1h / 100 if f1h is not None else None)
        # lecture 2
        l2 = cf.lecture_lignes(t.echeance, residuel)
        st.markdown("**Lecture 2 · Lignes encadrantes**")
        if l2["ok"]:
            a, b = st.columns(2)
            f2b = a.number_input(f"{l2['bas'].code} · {fdate(l2['bas'].echeance)} ({l2['bas'].jours} j) — {pct(l2['taux_bas'])}", value=None, placeholder="forcer", step=0.001, format="%.3f", key="f2b")
            f2h = b.number_input(f"{l2['haut'].code} · {fdate(l2['haut'].echeance)} ({l2['haut'].jours} j) — {pct(l2['taux_haut'])}", value=None, placeholder="forcer", step=0.001, format="%.3f", key="f2h")
            l2 = cf.lecture_lignes(t.echeance, residuel, f2b / 100 if f2b is not None else None, f2h / 100 if f2h is not None else None)
        # lecture 3
        st.markdown("**Lecture 3 · Deux lignes au choix**")
        codes_f = [l.code for l in cf.lignes if l.code]
        libf = lambda k: f"{k} · {fdate(next(x.echeance for x in cf.lignes if x.code == k))}"
        if len(codes_f) >= 2:
            a, b = st.columns(2)
            db = l2["bas"].code if l2.get("ok") else codes_f[0]; dh = l2["haut"].code if l2.get("ok") else codes_f[1]
            c3b = a.selectbox("Ligne basse", codes_f, index=codes_f.index(db) if db in codes_f else 0, format_func=libf, key="c3b")
            c3h = b.selectbox("Ligne haute", codes_f, index=codes_f.index(dh) if dh in codes_f else min(1, len(codes_f) - 1), format_func=libf, key="c3h")
            l3 = cf.lecture_choix(c3b, c3h, residuel)
            if l3["ok"]:
                f3b = a.number_input(f"courbe {pct(l3['taux_bas'])}", value=None, placeholder="forcer", step=0.001, format="%.3f", key="f3b")
                f3h = b.number_input(f"courbe {pct(l3['taux_haut'])}", value=None, placeholder="forcer", step=0.001, format="%.3f", key="f3h")
                l3 = cf.lecture_choix(c3b, c3h, residuel, f3b / 100 if f3b is not None else None, f3h / 100 if f3h is not None else None)
        else:
            l3 = dict(ok=False)
        # lecture 4 : taux d actualisation saisi a la main
        st.markdown("**Lecture 4 · Taux saisi**")
        base = {"1": l1["taux"], "2": l2["taux"] if l2.get("ok") else l1["taux"], "3": l3["taux"] if l3.get("ok") else l1["taux"]}
        defaut4 = round((base["2"] + spread / 10000) * 100, 3)
        t4 = st.number_input("Taux d'actualisation (%)", value=float(defaut4), step=0.001, format="%.3f", key="l4")
        l4 = dict(taux=t4 / 100)
        # methode retenue + main
        st.markdown("**Methode retenue**")
        opts = ["1 - Tenors", "2 - Lignes", "3 - Deux lignes", "4 - Taux saisi", "5 - Prix saisi"]
        choix = st.radio("Methode", opts, index=1 if l2.get("ok") else 0, label_visibility="collapsed")
        if choix.startswith("4"):
            r = l4["taux"]; r0 = r - spread / 10000
        elif choix.startswith("5"):
            typ = st.radio("Prix saisi", ["Plein", "Pied"], horizontal=True)
            px0 = st.number_input("Prix (%)", value=float(round(prix_plein(t, d, base["2"] + spread / 10000), 4)), step=0.01, format="%.4f", key="main_p")
            r = taux_depuis_prix(t, d, px0, plein=(typ == "Plein")); r0 = r - spread / 10000
        else:
            r0 = base[choix[0]]; r = r0 + spread / 10000
        aj = st.slider("Ajustement (pb)", -20, 20, 0, 1)
        r = r + aj / 10000
        for nom, val, det, on in (("TENORS", l1["taux"], f"{l1['borne_basse']} → {l1['borne_haute']}" + (f" · {l1['note']}" if l1['note'] else ""), choix.startswith("1")),
                                  ("LIGNES", l2["taux"] if l2.get("ok") else None, (("ligne elle-meme " + pct(l2['ligne_elle_meme']) + " · " if l2.get("ligne_elle_meme") else "") + f"{l2['bas'].code} → {l2['haut'].code}" + (f" · {l2['note']}" if l2.get('note') else "")) if l2.get("ok") else l2.get("message", ""), choix.startswith("2")),
                                  ("DEUX LIGNES", l3["taux"] if l3.get("ok") else None, f"{l3['bas'].code} → {l3['haut'].code}" if l3.get("ok") else "", choix.startswith("3")),
                                  ("TAUX SAISI", l4["taux"], "", choix.startswith("4"))):
            carte(nom, det, pct(val) if val is not None else "-", on)
    # ---------------- 3 resultat
    with z3:
        zone("3 · RESULTAT")
        v = valoriser(t, d, r)
        nominal = qte * t.nominal
        a, b = st.columns(2)
        with a:
            big("TAUX RETENU", pct(r), True); big("PRIX PIED", num(v.prix_pied) + " %")
        with b:
            big("PRIX PLEIN", num(v.prix_plein) + " %"); big("COUPON COURU", num(v.coupon_couru) + " %")
        conv = "TCN court : monetaire" if car.duree_initiale <= 366 else ("Residuel court : monetaire" if car.residuel <= 365 else "Actuariel")
        st.caption(f"{conv} · " + (f"taux d'actualisation saisi {pct(l4['taux'])}" if choix.startswith("4") else f"taux courbe {pct(r0)}") + (f" + ajustement {aj:+d} pb" if aj else ""))
        pc_m = nominal * t.taux_facial * ((car.premier_coupon - t.jouissance).days / car.base if d < car.premier_coupon else 1)
        st.table(pd.DataFrame({"Montants (MAD)": ["Nominal total", "Valeur pied de coupon", "Coupon couru", "Montant a regler", "Prochain coupon", "Montant du coupon", "Remboursement"],
                               "": [mnt(nominal), mnt(nominal * v.prix_pied / 100), mnt(nominal * v.coupon_couru / 100), mnt(nominal * v.prix_plein / 100), fdate(car.prochain_coupon), mnt(pc_m), mnt(nominal) + " le " + fdate(t.echeance)]}).set_index("Montants (MAD)"))
        st.table(pd.DataFrame({"Risque": ["Sensibilite", "Duration (ans)", "Convexite", "PVBP (MAD/pb)", "Sensi nominale (MAD/pb)", "Prix unitaire (MAD)", "vs tenors", "vs lignes"],
                               "": [num(v.sensi), num(v.duration, 3), num(v.convexite, 2), mnt(v.sensi * nominal * v.prix_plein / 100 * 1e-4, 1), mnt(nominal * v.sensi / 1e4), mnt(t.nominal * v.prix_plein / 100, 2), f"{(r0 - l1['taux'])*1e4:+.1f} pb", (f"{(r0 - l2['taux'])*1e4:+.1f} pb" if l2.get("ok") else "-")]}).set_index("Risque"))
        st.markdown("**Chocs**")
        st.dataframe(pd.DataFrame([{"Choc (pb)": x["choc"], "Taux": pct(r + x["choc"] / 1e4), "Prix plein": round(x["prix"], 4), "Variation (MAD)": round(x["valeur"])} for x in chocs(v.prix_plein, v.sensi, v.convexite, qte, t.nominal)]).style.map(rouge_vert, subset=["Variation (MAD)"]), hide_index=True, width="stretch")
        with st.expander("Autres dates"):
            rows = []
            for dd in (d, d + dt.timedelta(days=30), d + dt.timedelta(days=91), d + dt.timedelta(days=182), d + dt.timedelta(days=365)):
                if dd >= t.echeance:
                    continue
                rr = (cf.lecture_lignes(t.echeance, (t.echeance - dd).days)["taux"] if (choix.startswith("2") and l2.get("ok")) else cf.lecture_tenors((t.echeance - dd).days)["taux"]) + spread / 10000 + aj / 10000 if not choix.startswith(("4", "5")) else r
                vv = valoriser(t, dd, rr)
                rows.append(dict(Date=fdate(dd), Taux=pct(rr), **{"Prix plein": num(vv.prix_plein), "Prix pied": num(vv.prix_pied), "Sensi": num(vv.sensi)}))
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        if client:
            mem = memoire(store.operations(), store.flux(), ref, t.code, client, d)
            with st.expander(f"Memoire · {client} · {mem['taux_ratio']}", expanded=True):
                if mem["donnes"]:
                    st.caption("Derniers prix donnes sur cette ligne")
                    st.dataframe(pd.DataFrame([dict(Date=o["date"], Sens=o["sens"], MMAD=round(float(o["nominal"]) / 1e6), Prix=num(float(o["prix_plein"])), Taux=pct(float(o["taux"]))) for o in mem["donnes"]]), hide_index=True, width="stretch")
                if mem["demandes"]:
                    st.caption("Ce qu'il a demande sur cette ligne")
                    st.dataframe(pd.DataFrame([dict(Date=f["date"], Sens=f["sens"], MMAD=round(float(f["nominal"] or 0) / 1e6), Taux=pct(float(f["taux"])) if f.get("taux") else "") for f in mem["demandes"]]), hide_index=True, width="stretch")
                if mem["meme_tenor"]:
                    st.caption("Sur des lignes voisines")
                    st.dataframe(pd.DataFrame([dict(Date=o["date"], Ligne=o["code"], Sens=o["sens"], MMAD=round(float(o["nominal"]) / 1e6), Taux=pct(float(o["taux"]))) for o in mem["meme_tenor"]]), hide_index=True, width="stretch")
                if not (mem["donnes"] or mem["demandes"] or mem["meme_tenor"]):
                    st.caption("Rien avec ce client sur cette ligne.")
        st.session_state.dernier_titre = t.code; st.session_state.dernier_taux = r; st.session_state.dernier_prix = v.prix_plein
        c1, c2 = st.columns(2)
        if c1.button("Vers OPÉRER", type="primary"):
            st.session_state.prefill_op = dict(code=t.code, nominal=nominal, prix=v.prix_plein, taux=r, date=d)
            for k in ("op", "op_ech", "op_multi", "op_nom", "op_px", "op_tx"):
                st.session_state.pop(k, None)
            st.session_state.aller = "OPÉRER"; st.rerun()
        if c2.button("Vers SWAPPER"):
            st.session_state.prefill_swap = t.code; st.session_state.aller = "SWAPPER"; st.rerun()


# ================================================================= 3 - PORTEFEUILLE
def page_portefeuille():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>PORTEFEUILLE</span>&nbsp;&nbsp;<span style='color:#5E6675'></span>", unsafe_allow_html=True)
    if not courbe:
        st.warning("Aucune courbe disponible."); return
    dfp, base = positions_df(date_val)
    st.caption(f"Positions au {fdate(date_val)} · " + (f"photo du {fdate(base)}" if base else "aucune photo") + " + operations")
    g, dr = st.columns([1, 1])
    with g:
        up = st.file_uploader("Photo de positions", type=["xlsx", "csv"], key="pos")
        if up is not None:
            try:
                dfu = pd.read_excel(up) if up.name.endswith("xlsx") else pd.read_csv(up, sep=None, engine="python")
                dfu.columns = [str(c).strip().lower() for c in dfu.columns]
                dph = pd.to_datetime(dfu["date"].iloc[0]).date() if "date" in dfu.columns else date_val
                if st.button(f"Enregistrer au {fdate(dph)}", type="primary", disabled=not peut_ecrire):
                    store.enregistrer_photo(dph, [dict(code=str(r["code"]).strip(), quantite=r["quantite"], spread="") for _, r in dfu.iterrows() if pd.notna(r.get("quantite"))])
                    st.success("Photo enregistree."); st.rerun()
            except Exception as e:
                st.error(f"Fichier illisible : {e}")
    with dr:
        st.download_button("Canevas positions", excel_bytes({"Positions": pd.DataFrame([dict(date=date_val, code="201898", quantite=100)])}), "canevas_positions.xlsx")
        ph = store.photos()
        if ph:
            st.caption("Photos : " + ", ".join(fdate(d) for d in sorted(ph)))
    if dfp.empty:
        st.info("Aucune position."); return
    pos = [(r["code"], r["quantite"], r["spread"]) for _, r in dfp.iterrows()]
    lignes = valoriser_portefeuille(pos, ref, courbe, date_val, methode)
    inconnus = [p[0] for p in pos if p[0] not in ref]
    if inconnus:
        st.warning("Codes inconnus : " + ", ".join(inconnus))
    ag = agregats(lignes)
    k = st.columns(5)
    k[0].metric("Valeur de marche (MAD)", mnt(ag["valeur_marche"])); k[1].metric("Nominal (MAD)", mnt(ag["nominal"])); k[2].metric("Sensibilite", num(ag["sensi"], 3)); k[3].metric("Duration (ans)", num(ag["duration"], 3)); k[4].metric("PVBP (MAD/pb)", mnt(ag["pvbp"]))
    k = st.columns(5)
    k[0].metric("Coupon couru (MAD)", mnt(ag["coupon_couru"])); k[1].metric("Convexite", num(ag["convexite"], 1)); k[2].metric("Sensi nominale (MAD/pb)", mnt(ag["sensi_nominale"])); k[3].metric("Lignes", str(ag["nb"])); k[4].metric("Poids ligne max", pct(ag["poids_max"], 1))
    onglets = st.tabs(["Ligne a ligne", "Tranches", "Limites"])
    with onglets[0]:
        df = pd.DataFrame([dict(Code=l.code, Libelle=l.libelle, Quantite=l.quantite, Nominal=l.nominal, Echeance=fdate(l.echeance), Maturite=round(l.maturite, 2), **{"Taux courbe": pct(l.taux_courbe), "Taux actu.": pct(l.taux_actu), "Prix plein": round(l.prix_plein, 4), "Valeur": round(l.valeur_marche), "Couru": round(l.coupon_couru), "Sensi": round(l.sensi, 4), "Duration": round(l.duration, 3), "PVBP": round(l.pvbp, 1), "Sensi nominale": round(l.sensi_nominale), "Convexite": round(l.convexite, 2), "Lecture": l.note}) for l in lignes])
        st.dataframe(df, hide_index=True, width="stretch")
        st.download_button("Exporter", excel_bytes({"Valorisation": df}), f"valorisation_{date_val.isoformat()}.xlsx")
    with onglets[1]:
        st.dataframe(pd.DataFrame([dict(Tranche=t["tranche"], **{"Valeur (MAD)": mnt(t["valeur"]), "Poids": pct(t["poids"], 1), "Sensi nominale": mnt(t["sensi_nominale"]), "Lignes": t["nb"]}) for t in tranches(lignes)]), hide_index=True, width="stretch")
    with onglets[2]:
        g = {"nominal": [tuple(x) for x in par["limites_nominal"]], "sensi": [tuple(x) for x in par["limites_sensi"]]}
        dl = pd.DataFrame([dict(Palier=x["palier"], Consommation=mnt(x["consommation"]), Limite=mnt(x["limite"]), Utilisation=pct(x["utilisation"], 1), Restant=mnt(x["restant"]), Statut=x["statut"]) for x in limites(lignes, g)])
        st.dataframe(dl.style.map(lambda v: f"color:{ROUGE};font-weight:700" if v == "DEPASSEMENT" else ("color:#E5541E;font-weight:700" if v == "Vigilance" else f"color:{VERT}"), subset=["Statut"]), hide_index=True, width="stretch")


# ================================================================= 4 - OPERATIONS
def _mail_operation(o: dict, t, nous_vendons: bool) -> tuple:
    """Objet, corps, A, Cc pour une operation (bloc ou ventilation)."""
    tp = tiers_par_nom()
    dest = emails_de(o.get("contrepartie", ""), "A"); cc = emails_de(o.get("contrepartie", ""), "Cc")
    if o.get("client"):
        cc += emails_de(o["client"], "A")
    dep = tp.get(o.get("contrepartie", ""), {}).get("depositaire", "")
    if dep:
        cc += emails_de(dep, "A")
    nous = "vendons" if nous_vendons else "achetons"; vous = "achetez" if nous_vendons else "vendez"
    nominal = float(o["nominal"]); px = float(o["prix_plein"]); r = float(o["taux"]); montant = nominal * px / 100
    objet = f"Confirmation - {o['sens']} {t.libelle if t else o['code']} - {mnt(nominal)} MAD - valeur {fdate(dt.date.fromisoformat(o['date_valeur'])) if o.get('date_valeur') else ''}"
    lignes = [f"Sens : {o['sens']} (nous {nous}, vous {vous})", f"Titre : {t.libelle if t else o['code']}", f"Code : {o['code']}" + (f" - ISIN : {t.isin}" if t and t.isin else ""),
              (f"Echeance : {fdate(t.echeance)} - coupon {pct(t.taux_facial, 2)}" if t else ""), f"Nominal : {mnt(nominal)} MAD", f"Prix plein : {num(px)} %", f"Taux : {pct(r)}",
              f"Date d'operation : {fdate(dt.date.fromisoformat(o['date']))}", f"Date valeur : {fdate(dt.date.fromisoformat(o['date_valeur'])) if o.get('date_valeur') else '-'}", f"Montant a regler : {mnt(montant, 2)} MAD"]
    if o.get("client"): lignes.append(f"Pour le compte de : {o['client']}")
    if o.get("fonds"): lignes.append(f"Fonds : {o['fonds']}" + (f" - depositaire : {dep}" if dep else ""))
    corps = "Bonjour,\n\nNous confirmons l'operation suivante :\n\n" + "\n".join(l for l in lignes if l) + "\n\nMerci de nous confirmer par retour.\n\nCordialement,\nSalle des marches - Credit du Maroc"
    return objet, corps, sorted(set(dest)), sorted(set(cc) - set(dest))


def _nouvel_id(ops):
    return str(max([int(o["id"]) for o in ops if str(o.get("id", "")).isdigit()] + [0]) + 1)


def page_operations():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>OPÉRER</span>", unsafe_allow_html=True)
    pre = st.session_state.get("prefill_op") or {}
    tp = tiers_par_nom(); noms = sorted(tp) or sorted({x["contrepartie"] for x in store.contacts() if x.get("contrepartie")})
    g, dr = st.columns([1.5, 1])
    with g:
        mode = st.radio("Mode", ["Simple", "Intermediation"], horizontal=True, label_visibility="collapsed")
        if mode == "Simple":
            st.subheader("Saisie")
            c1, c2, c3 = st.columns([1, 1, 1.6])
            d = c1.date_input("Date d'operation", value=pre.get("date", date_val), format="DD/MM/YYYY", key="dop")
            dv = c2.date_input("Date valeur", value=d + dt.timedelta(days=1), format="DD/MM/YYYY", key="dvop")
            with c3:
                t = choisir_titre("op", d)
            if not t:
                return
            sens = st.radio("Sens", ["Achat", "Vente"], horizontal=True)
            c = courbe_active(d); r_c = c.taux_pour(t.echeance, d, methode)[0] if c else t.taux_facial
            c1, c2, c3 = st.columns(3)
            nominal = c1.number_input("Nominal (MAD)", value=int(pre.get("nominal", 10_000_000)), step=1_000_000, min_value=0, key="op_nom")
            mp = c2.radio("Saisir", ["prix plein", "taux"], horizontal=True)
            if mp == "prix plein":
                px = c3.number_input("Prix plein (%)", value=float(round(pre.get("prix", prix_plein(t, d, r_c)), 4)), step=0.01, format="%.4f", key="op_px"); r = taux_depuis_prix(t, d, px)
            else:
                r = c3.number_input("Taux (%)", value=float(round(pre.get("taux", r_c) * 100, 3)), step=0.001, format="%.3f", key="op_tx") / 100; px = prix_plein(t, d, r)
            c1, c2, c3, c4 = st.columns(4)
            cp = c1.selectbox("Contrepartie", [""] + noms, key="op_cp")
            cl = c2.selectbox("Pour le compte de (option)", [""] + noms, key="op_cl", help="client final quand on passe par un intermediaire")
            canal = c3.selectbox("Canal", CANAUX, key="op_canal")
            com = c4.text_input("Commentaire")
            k = st.columns(4); k[0].metric("Prix plein", num(px) + " %"); k[1].metric("Taux", pct(r)); k[2].metric("Montant (MAD)", mnt(nominal * px / 100)); k[3].metric("vs courbe", f"{(r - r_c)*1e4:+.1f} pb")
            if st.button("Enregistrer", type="primary", disabled=not peut_ecrire):
                ops = store.operations(); nid = _nouvel_id(ops)
                ops.append(dict(id=nid, date=d.isoformat(), date_valeur=dv.isoformat(), sens=sens, code=t.code, quantite=f"{nominal / t.nominal:.6f}", nominal=f"{nominal:.2f}", prix_plein=f"{px:.6f}", taux=f"{r:.6f}",
                                contrepartie=cp, client=cl, fonds="", parent_id="", intermediation_id="", canal=canal, nature="", commentaire=com, saisie_le=dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
                store.enregistrer_operations(ops); st.session_state.pop("prefill_op", None); st.session_state.brouillon = [nid]; st.rerun()
        else:
            st.subheader("Intermediation")
            st.caption("Vendeurs et acheteurs en nombre libre, dates libres, la vente peut preceder l'achat ; les deux cotes doivent avoir le meme total.")
            t = choisir_titre("op", date_val)
            if not t:
                return
            c = courbe_active(date_val); r_c = c.taux_pour(t.echeance, date_val, methode)[0] if c else t.taux_facial
            px_def = round(prix_plein(t, date_val, r_c), 4)
            cfg = {"tiers": st.column_config.SelectboxColumn("Tiers", options=noms, required=True), "client": st.column_config.SelectboxColumn("Pour le compte de", options=[""] + noms), "nominal": st.column_config.NumberColumn("Nominal (MAD)", step=1_000_000, format="%d"),
                   "date_op": st.column_config.DateColumn("Date op.", format="DD/MM/YYYY"), "date_valeur": st.column_config.DateColumn("Date valeur", format="DD/MM/YYYY"), "prix_plein": st.column_config.NumberColumn("Prix plein (%)", format="%.4f", step=0.01)}
            j1, j2 = st.columns(2)
            with j1:
                st.markdown("**Vendeurs (j'achete)**")
                dfv = st.data_editor(st.session_state.get("int_v", pd.DataFrame([dict(tiers=noms[0] if noms else "", client="", nominal=10_000_000, date_op=date_val, date_valeur=date_val + dt.timedelta(days=1), prix_plein=px_def)])), num_rows="dynamic", width="stretch", key="ed_int_v", column_config=cfg)
            with j2:
                st.markdown("**Acheteurs (je vends)**")
                dfa = st.data_editor(st.session_state.get("int_a", pd.DataFrame([dict(tiers=noms[1] if len(noms) > 1 else "", client="", nominal=10_000_000, date_op=date_val + dt.timedelta(days=1), date_valeur=date_val + dt.timedelta(days=2), prix_plein=px_def)])), num_rows="dynamic", width="stretch", key="ed_int_a", column_config=cfg)
            def _jambes(df, sens):
                out = []
                for _, r in df.iterrows():
                    if not r.get("tiers") or pd.isna(r.get("nominal")) or not r["nominal"]: continue
                    d_ = pd.to_datetime(r["date_op"]).date(); dv_ = pd.to_datetime(r["date_valeur"]).date() if pd.notna(r.get("date_valeur")) else d_ + dt.timedelta(days=1)
                    px_ = float(r["prix_plein"]) if pd.notna(r.get("prix_plein")) else px_def
                    out.append(dict(sens=sens, tiers=str(r["tiers"]), client=str(r.get("client", "") or ""), nominal=float(r["nominal"]), date=d_, date_valeur=dv_, px=px_, taux=taux_depuis_prix(t, d_, px_)))
                return out
            achats = _jambes(dfv, "Achat"); ventes = _jambes(dfa, "Vente")
            tot_a = sum(x["nominal"] for x in achats); tot_v = sum(x["nominal"] for x in ventes)
            cout = sum(x["nominal"] * x["px"] / 100 for x in achats); produit = sum(x["nominal"] * x["px"] / 100 for x in ventes)
            # financement : chaque achat porte jusqu a la date valeur moyenne (ponderee) des ventes
            dv_moy = (sum(x["nominal"] * x["date_valeur"].toordinal() for x in ventes) / tot_v) if tot_v else None
            fin = -sum(x["nominal"] * x["px"] / 100 * par["taux_financement"] * (dv_moy - x["date_valeur"].toordinal()) / 360 for x in achats) if dv_moy else 0.0   # jours negatifs = vente avant achat : gain de tresorerie
            k = st.columns(5); k[0].metric("Achete (MAD)", mnt(tot_a)); k[1].metric("Vendu (MAD)", mnt(tot_v)); k[2].metric("Marge", mnt(produit - cout)); k[3].metric("Financement", mnt(fin)); k[4].metric("Resultat", mnt(produit - cout + fin))
            if achats and ventes:
                st.caption("Taux : " + " · ".join(f"{x['sens'].lower()} {x['tiers']} {pct(x['taux'])}" for x in achats + ventes))
            ok = achats and ventes and abs(tot_a - tot_v) < 1
            if abs(tot_a - tot_v) >= 1: st.warning(f"Les deux cotes different de {mnt(abs(tot_a - tot_v))} MAD.")
            if st.button("Enregistrer l'intermediation", type="primary", disabled=(not ok or not peut_ecrire)):
                ops = store.operations(); iid = "I" + _nouvel_id(ops); ids = []
                for x in achats + ventes:
                    nid = _nouvel_id(ops); ids.append(nid)
                    ops.append(dict(id=nid, date=x["date"].isoformat(), date_valeur=x["date_valeur"].isoformat(), sens=x["sens"], code=t.code, quantite=f"{x['nominal'] / t.nominal:.6f}", nominal=f"{x['nominal']:.2f}", prix_plein=f"{x['px']:.6f}", taux=f"{x['taux']:.6f}",
                                    contrepartie=x["tiers"], client=x["client"], fonds="", parent_id="", intermediation_id=iid, canal="Marche", nature="Intermediation", commentaire="intermediation", saisie_le=dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
                store.enregistrer_operations(ops); st.session_state.brouillon = ids; st.rerun()
        # ---------------- brouillons de mail
        br = st.session_state.get("brouillon")
        if br:
            ops = store.operations()
            for oid in br:
                o = next((x for x in ops if x["id"] == oid), None)
                if not o: continue
                tb = ref.get(o["code"]); objet, corps, dest, cc = _mail_operation(o, tb, o["sens"] == "Vente")
                with st.expander(f"Mail · {o['sens']} {o['contrepartie'] or '?'} · {mnt(float(o['nominal']))} MAD" + (f" · {o['fonds']}" if o.get("fonds") else ""), expanded=True):
                    if not dest: st.warning("Aucun e-mail pour ce tiers : atelier CONTACTS.")
                    st.text_input("A", "; ".join(dest), key=f"m_a{oid}"); st.text_input("Cc", "; ".join(cc), key=f"m_cc{oid}"); st.text_area("Corps", corps, height=230, key=f"m_c{oid}")
                    lien = "mailto:" + ",".join(dest) + "?" + urllib.parse.urlencode({"cc": ",".join(cc), "subject": objet, "body": corps}, quote_via=urllib.parse.quote)
                    c1, c2 = st.columns(2); c1.link_button("Ouvrir dans la messagerie", lien, type="primary")
                    c2.download_button("Ticket PDF", ticket_pdf(o, tb, user["nom"], pct, mnt), f"ticket_{oid}.pdf", "application/pdf", key=f"tk{oid}")
            if st.button("Fermer les brouillons"):
                st.session_state.pop("brouillon", None); st.rerun()
    with dr:
        st.subheader("Import")
        st.download_button("Canevas operations", excel_bytes({"Operations": pd.DataFrame([dict(date=date_val, date_valeur=date_val + dt.timedelta(days=1), sens="Achat", code="201898", nominal=10000000, prix_plein="", taux=3.85, contrepartie="Banque X", client="", canal="Marche", commentaire="")])}), "canevas_operations.xlsx")
        up = st.file_uploader("Fichier", type=["xlsx", "csv"], key="ops")
        if up is not None:
            try:
                dfu = pd.read_excel(up) if up.name.endswith("xlsx") else pd.read_csv(up, sep=None, engine="python"); dfu.columns = [str(c).strip().lower() for c in dfu.columns]
                st.dataframe(dfu, hide_index=True, width="stretch")
                if st.button("Importer", type="primary", disabled=not peut_ecrire):
                    ops = store.operations(); n = 0
                    for _, r in dfu.iterrows():
                        code = str(r.get("code", "")).strip(); t2 = ref.get(code)
                        if not t2: continue
                        dd = pd.to_datetime(r["date"]).date(); ddv = pd.to_datetime(r["date_valeur"]).date() if pd.notna(r.get("date_valeur")) and r.get("date_valeur") not in ("", None) else dd + dt.timedelta(days=1)
                        nominal = float(r["nominal"]) if pd.notna(r.get("nominal")) and r.get("nominal") != "" else float(r.get("quantite", 0)) * t2.nominal
                        if pd.notna(r.get("prix_plein")) and r.get("prix_plein") not in ("", None):
                            px = float(r["prix_plein"]); rr = taux_depuis_prix(t2, dd, px)
                        elif pd.notna(r.get("taux")) and r.get("taux") not in ("", None):
                            rr = float(r["taux"]); rr = rr / 100 if rr > 1 else rr; px = prix_plein(t2, dd, rr)
                        else:
                            cc_ = courbe_active(dd); rr = cc_.taux_pour(t2.echeance, dd, methode)[0] if cc_ else t2.taux_facial; px = prix_plein(t2, dd, rr)
                        n += 1
                        ops.append(dict(id=_nouvel_id(ops), date=dd.isoformat(), date_valeur=ddv.isoformat(), sens="Achat" if str(r.get("sens", "Achat")).lower().startswith("a") else "Vente", code=code, quantite=f"{nominal / t2.nominal:.6f}", nominal=f"{nominal:.2f}",
                                        prix_plein=f"{px:.6f}", taux=f"{rr:.6f}", contrepartie=str(r.get("contrepartie", "") or ""), client=str(r.get("client", "") or ""), fonds="", parent_id="", intermediation_id="", canal=str(r.get("canal", "Marche") or "Marche"), nature="", commentaire=str(r.get("commentaire", "") or ""), saisie_le=dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
                    store.enregistrer_operations(ops); st.rerun()
            except Exception as e:
                st.error(f"Fichier illisible : {e}")
        # ---------------- ventilation sur les fonds
        st.subheader("Ventiler sur les fonds")
        ops = store.operations()
        blocs = [o for o in ops if not o.get("parent_id") and tp.get(o.get("contrepartie", ""), {}).get("type") == "SDG"]
        if blocs:
            choix = st.selectbox("Operation en bloc", [""] + [f"{o['id']} · {o['sens']} {o['contrepartie']} {mnt(float(o['nominal']))} MAD {ref[o['code']].libelle if o['code'] in ref else o['code']}" for o in blocs])
            if choix:
                bo = next(o for o in blocs if o["id"] == choix.split(" · ")[0])
                fonds = [t2["nom"] for t2 in store.tiers() if t2.get("type") == "Fonds" and t2.get("parent") == bo["contrepartie"]]
                deja = [o for o in ops if o.get("parent_id") == bo["id"]]
                if deja:
                    st.caption("Deja ventile : " + ", ".join(f"{o['fonds']} {mnt(float(o['nominal']))}" for o in deja))
                if fonds:
                    dfv = st.data_editor(pd.DataFrame([dict(fonds=f, nominal=0) for f in fonds]), hide_index=True, width="stretch", key="edvent", column_config={"fonds": st.column_config.TextColumn("Fonds"), "nominal": st.column_config.NumberColumn("Nominal (MAD)", step=1_000_000, format="%d")})
                    tot = float(dfv["nominal"].fillna(0).sum()); cible = float(bo["nominal"])
                    st.caption(f"Total {mnt(tot)} / bloc {mnt(cible)} MAD" + ("" if abs(tot - cible) < 1 else f" · reste {mnt(cible - tot)}"))
                    if st.button("Enregistrer la ventilation", type="primary", disabled=(abs(tot - cible) >= 1 or not peut_ecrire)):
                        ops = [o for o in ops if o.get("parent_id") != bo["id"]]; ids = []
                        for _, r in dfv.iterrows():
                            if not r["nominal"]: continue
                            nid = _nouvel_id(ops); ids.append(nid); t2 = ref.get(bo["code"])
                            ops.append(dict(bo, id=nid, nominal=f"{float(r['nominal']):.2f}", quantite=f"{float(r['nominal']) / t2.nominal:.6f}" if t2 else "", contrepartie=r["fonds"], fonds=r["fonds"], parent_id=bo["id"], commentaire=f"ventilation de {bo['id']}", saisie_le=dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
                        store.enregistrer_operations(ops); st.session_state.brouillon = ids; st.rerun()
                else:
                    st.caption("Aucun fonds rattache a cette SDG : atelier CONTACTS.")
        else:
            st.caption("Aucune operation en bloc avec une SDG.")
    # ---------------- journal
    st.subheader("Journal")
    ops = store.operations()
    if ops:
        rows = []
        for o in sorted(ops, key=lambda o: (o["date"], o["id"]), reverse=True):
            rows.append({"id": o["id"], "Date op.": o["date"], "Date valeur": o.get("date_valeur", ""), "Sens": o["sens"], "Code": o["code"], "Libelle": ref[o["code"]].libelle if o["code"] in ref else "", "Nominal": mnt(float(o["nominal"])) if o.get("nominal") else "",
                         "Prix": num(float(o["prix_plein"])) if o.get("prix_plein") else "", "Taux": pct(float(o["taux"])) if o.get("taux") else "", "Contrepartie": o.get("contrepartie", ""), "Pour le compte de": o.get("client", ""),
                         "Fonds": o.get("fonds", ""), "Canal": o.get("canal", ""), "Nature": o.get("nature", ""), "Lien": ("↳ " + o["parent_id"]) if o.get("parent_id") else (o.get("intermediation_id", "") or ""), "Commentaire": o.get("commentaire", "")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        inter = {}
        for o in ops:
            if o.get("intermediation_id") and not o.get("parent_id"): inter.setdefault(o["intermediation_id"], []).append(o)
        if inter:
            st.caption("Intermediations")
            ri = []
            for k2, L in inter.items():
                A = [x for x in L if x["sens"] == "Achat"]; V = [x for x in L if x["sens"] == "Vente"]
                if not (A and V): continue
                na = sum(float(x["nominal"]) for x in A); nv = sum(float(x["nominal"]) for x in V)
                cout = sum(float(x["nominal"]) * float(x["prix_plein"]) / 100 for x in A); prod = sum(float(x["nominal"]) * float(x["prix_plein"]) / 100 for x in V)
                dvm = sum(float(x["nominal"]) * dt.date.fromisoformat(x.get("date_valeur") or x["date"]).toordinal() for x in V) / nv
                fin = -sum(float(x["nominal"]) * float(x["prix_plein"]) / 100 * par["taux_financement"] * (dvm - dt.date.fromisoformat(x.get("date_valeur") or x["date"]).toordinal()) / 360 for x in A)
                ri.append({"Lien": k2, "Titre": ref[A[0]["code"]].libelle if A[0]["code"] in ref else A[0]["code"], "Achete": mnt(na), "Vendeurs": ", ".join(f"{x['contrepartie']} {float(x['nominal'])/1e6:.0f} M @ {num(float(x['prix_plein']))} / {pct(float(x['taux']))}" for x in A),
                           "Vendu": mnt(nv), "Acheteurs": ", ".join(f"{x['contrepartie']} {float(x['nominal'])/1e6:.0f} M @ {num(float(x['prix_plein']))} / {pct(float(x['taux']))}" for x in V), "Marge": mnt(prod - cout), "Financement": mnt(fin), "Resultat": mnt(prod - cout + fin)})
            st.dataframe(pd.DataFrame(ri), hide_index=True, width="stretch")
        st.subheader("Operation selectionnee")
        lib_op = lambda o: f"{o['id']} · {o['date']} · {o['sens']} {mnt(float(o['nominal']))} {ref[o['code']].libelle if o['code'] in ref else o['code']} · {o.get('contrepartie', '')}" + (" · ventilation" if o.get("parent_id") else "")
        choix_op = st.selectbox("Operation", [""] + [lib_op(o) for o in sorted(ops, key=lambda o: (o["date"], o["id"]), reverse=True)], key="sel_op")
        if choix_op:
            oid = choix_op.split(" · ")[0]; o = next(x for x in ops if x["id"] == oid); t = ref.get(o["code"])
            with st.form("modif_op"):
                c1, c2, c3, c4 = st.columns(4)
                nd = c1.date_input("Date d'operation", value=dt.date.fromisoformat(o["date"]), format="DD/MM/YYYY")
                ndv = c2.date_input("Date valeur", value=dt.date.fromisoformat(o["date_valeur"]) if o.get("date_valeur") else dt.date.fromisoformat(o["date"]) + dt.timedelta(days=1), format="DD/MM/YYYY")
                nsens = c3.selectbox("Sens", ["Achat", "Vente"], index=0 if o["sens"] == "Achat" else 1)
                ncode = c4.text_input("Code", o["code"])
                c1, c2, c3, c4 = st.columns(4)
                nnom = c1.number_input("Nominal (MAD)", value=float(o["nominal"] or 0), step=1_000_000.0, format="%.0f")
                nmode = c2.radio("Je modifie", ["le prix plein", "le taux"], horizontal=True)
                npx = c3.number_input("Prix plein (%)", value=float(o["prix_plein"] or 100), step=0.01, format="%.4f")
                ntx = c4.number_input("Taux (%)", value=float(o["taux"] or 0) * 100, step=0.001, format="%.3f")
                c1, c2, c3 = st.columns(3)
                ncp = c1.selectbox("Contrepartie", [""] + noms, index=([""] + noms).index(o.get("contrepartie", "")) if o.get("contrepartie", "") in noms else 0)
                ncl = c2.selectbox("Pour le compte de", [""] + noms, index=([""] + noms).index(o.get("client", "")) if o.get("client", "") in noms else 0)
                ncom = c3.text_input("Commentaire", o.get("commentaire", ""))
                b1, b2, b3, b4 = st.columns(4)
                modifier = b1.form_submit_button("Enregistrer les modifications", type="primary", disabled=not peut_ecrire)
                preparer = b2.form_submit_button("Mail / ticket")
                supprimer = b3.form_submit_button("Supprimer", disabled=not peut_ecrire)
                dupliquer = b4.form_submit_button("Dupliquer")
            if modifier:
                t2 = ref.get(ncode.strip())
                if not t2:
                    st.error("Code inconnu.")
                else:
                    if nmode == "le prix plein":
                        px2 = npx; r2 = taux_depuis_prix(t2, nd, px2)
                    else:
                        r2 = ntx / 100; px2 = prix_plein(t2, nd, r2)
                    o.update(date=nd.isoformat(), date_valeur=ndv.isoformat(), sens=nsens, code=t2.code, quantite=f"{nnom / t2.nominal:.6f}", nominal=f"{nnom:.2f}", prix_plein=f"{px2:.6f}", taux=f"{r2:.6f}", contrepartie=ncp, client=ncl, commentaire=ncom, saisie_le=dt.datetime.now().strftime("%Y-%m-%d %H:%M") + f" (modifie par {user['nom']})")
                    for v in ops:                       # les ventilations suivent le bloc : dates, sens, code, prix, taux
                        if v.get("parent_id") == oid:
                            v.update(date=o["date"], date_valeur=o["date_valeur"], sens=o["sens"], code=o["code"], prix_plein=o["prix_plein"], taux=o["taux"])
                    store.enregistrer_operations(ops); st.rerun()
            if preparer:
                st.session_state.brouillon = [oid]; st.rerun()
            if supprimer:
                store.enregistrer_operations([x for x in ops if x["id"] != oid and x.get("parent_id") != oid]); st.rerun()
            if dupliquer:
                n = dict(o); n["id"] = _nouvel_id(ops); n["parent_id"] = ""; n["intermediation_id"] = ""; n["fonds"] = ""; n["commentaire"] = (o.get("commentaire", "") + " (copie)").strip(); n["saisie_le"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                ops.append(n); store.enregistrer_operations(ops); st.rerun()
            vent = [x for x in ops if x.get("parent_id") == oid]
            if vent:
                st.caption("Ventilations : " + " · ".join(f"{x['fonds']} {mnt(float(x['nominal']))}" for x in vent))
        st.download_button("Exporter", excel_bytes({"Operations": pd.DataFrame(ops)}), "operations.xlsx")
    else:
        st.info("Aucune operation.")


# ================================================================= 5 - P&L
def page_pnl():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>P&L</span>&nbsp;&nbsp;<span style='color:#5E6675'></span>", unsafe_allow_html=True)
    dates = sorted(courbes_dispo)
    if len(dates) < 2:
        st.info("Deux courbes au moins."); return
    ph = sorted(store.photos())
    a, b, c3 = st.columns(3)
    d0 = a.selectbox("Du", dates, index=max(0, dates.index(min([x for x in dates if ph and x >= ph[0]] or [dates[0]]))), format_func=fdate)
    d1 = b.selectbox("Au", dates, index=len(dates) - 1, format_func=fdate)
    tf = c3.number_input("Financement (%)", value=float(par["taux_financement"] * 100), step=0.05, format="%.2f") / 100
    base_pl = st.radio("Base", ["operation", "valeur"], horizontal=True, format_func=lambda b: "Date d'operation" if b == "operation" else "Date valeur", key="base_pl")
    rows = pnl_journalier(store, ref, d0, d1, methode, tf, base_pl)
    if not rows:
        st.info("Rien a calculer."); return
    tot = {k: sum(r[k] for r in rows) for k in ("carry", "effet_courbe", "trading", "financement", "total", "flux_encaisses", "cash_operations")}
    k = st.columns(5)
    k[0].metric("P&L total (MAD)", mnt(tot["total"])); k[1].metric("Carry", mnt(tot["carry"])); k[2].metric("Effet courbe", mnt(tot["effet_courbe"])); k[3].metric("Trading", mnt(tot["trading"])); k[4].metric("Financement", mnt(tot["financement"]))
    df = pd.DataFrame([dict(Du=fdate(r["de"]), Au=fdate(r["a"]), Jours=r["jours"], **{"Valeur debut": round(r["vm_debut"]), "Valeur fin": round(r["vm_fin"]), "Carry": round(r["carry"]), "Effet courbe": round(r["effet_courbe"]), "Trading": round(r["trading"]), "Financement": round(r["financement"]), "P&L total": round(r["total"]), "Flux encaisses": round(r["flux_encaisses"]), "Operations": r["nb_operations"]}) for r in rows])
    st.dataframe(df.style.map(rouge_vert, subset=["Carry", "Effet courbe", "Trading", "Financement", "P&L total"]), hide_index=True, width="stretch")
    cum = pd.DataFrame({"Date": [fdate(r["a"]) for r in rows], "P&L cumule": pd.Series([r["total"] for r in rows]).cumsum().values}).set_index("Date")
    st.line_chart(cum)
    st.download_button("Exporter", excel_bytes({"PnL": df}), f"pnl_{d0.isoformat()}_{d1.isoformat()}.xlsx")


# ================================================================= 6 - SWAP
def page_swap():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>SWAPPER</span>&nbsp;&nbsp;<span style='color:#5E6675'></span>", unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        d_a = st.date_input("Date aller", value=date_val, format="DD/MM/YYYY", key="dsa")
        d_r = st.date_input("Date retour", value=date_val + dt.timedelta(days=91), format="DD/MM/YYYY", key="dsr")
        volume = st.number_input("Volume (MAD)", value=100_000_000, step=10_000_000, min_value=1_000_000)
        mode = st.radio("Mode", ["sensi", "volume"], format_func=lambda m: "Sensi egale" if m == "sensi" else "Volume egal", horizontal=True)
        tf = st.number_input("Financement (%)", value=float(par["taux_financement"] * 100), step=0.05, format="%.2f") / 100
    codes = [k for k in sorted(ref, key=lambda k: ref[k].echeance) if ref[k].echeance > d_r]
    opt = {f"{k} - {ref[k].libelle}": k for k in codes}
    with b:
        pref_s = st.session_state.get("prefill_swap", "201898")
        mes = st.multiselect("Mes lignes", list(opt), default=[x for x in opt if x.startswith(pref_s + " ")][:1])
        cps = st.multiselect("Lignes contrepartie", list(opt), default=[x for x in opt if x.startswith("201896")][:1])
    if not mes or not cps:
        st.info("Une ligne de chaque cote."); return
    ca = courbe_active(d_a); cr = courbe_active(d_r) or ca
    if not ca:
        st.warning("Aucune courbe a la date aller."); return
    sw = simuler([(opt[m], 1) for m in mes], [(opt[c], 1) for c in cps], ref, ca, cr, d_a, d_r, mode, float(volume), methode, tf)
    if not sw["ok"]:
        st.warning(sw["message"]); return
    st.caption(f"Aller : {ca.source} · retour : {cr.source}")
    k = st.columns(5)
    k[0].metric("Nominal donne", mnt(sw["nominal_mes"])); k[1].metric("Nominal recu", mnt(sw["nominal_cp"])); k[2].metric("PVBP donne / recu", f"{mnt(sw['pvbp_mes'])} / {mnt(sw['pvbp_cp'])}"); k[3].metric("Soulte (MAD)", mnt(sw["soulte"])); k[4].metric("Duree (jours)", str(sw["jours"]))
    st.subheader("A l'aller")
    def jambe(lst, titre):
        st.markdown(f"**{titre}**")
        st.dataframe(pd.DataFrame([dict(Code=x["code"], Libelle=x["libelle"], Echeance=fdate(x["echeance"]), Maturite=round(x["maturite"], 2), Nominal=round(x["nominal"]), Taux=pct(x["taux"]), **{"Prix plein": num(x["prix_plein"]), "Valeur": round(x["valeur"]), "Couru": round(x["couru"]), "Sensi": num(x["sensi"]), "PVBP": round(x["pvbp"]), "Sensi nominale": round(x["sensi_nominale"])}) for x in lst]), hide_index=True, width="stretch")
    jambe(sw["mes"], "Je donne"); jambe(sw["cp"], "Je recois")
    st.subheader("Resultat")
    k = st.columns(5)
    k[0].metric("Carry recu", mnt(sw["carry_recu"])); k[1].metric("Carry donne", mnt(sw["carry_donne"])); k[2].metric("Carry net", mnt(sw["carry_net"])); k[3].metric("Financement", mnt(sw["financement"])); k[4].metric("P&L prix d'aller", mnt(sw["pnl_prix_aller"]))
    k = st.columns(4)
    k[0].metric("MtM recu", mnt(sw["mtm_recu"])); k[1].metric("MtM donne", mnt(sw["mtm_donne"])); k[2].metric("MtM net", mnt(sw["mtm_net"])); k[3].metric("P&L marche", mnt(sw["pnl_marche"]))
    st.caption(f"Sensi nominale : {mnt(sw['sensi_nominale_mes'])} → {mnt(sw['sensi_nominale_cp'])} MAD/pb")
    st.download_button("Exporter", excel_bytes({"Donne": pd.DataFrame(sw["mes"]), "Recu": pd.DataFrame(sw["cp"]), "Donne_retour": pd.DataFrame(sw["mes_retour"]), "Recu_retour": pd.DataFrame(sw["cp_retour"])}), "swap.xlsx")


# ================================================================= REFERENTIEL / PARAMETRES
def page_referentiel():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>RÉFÉRENTIEL</span>", unsafe_allow_html=True)
    st.caption(f"{len(ref)} titres")
    up = st.file_uploader("Remplacer", type=["xlsx", "csv"], key="refup")
    if up is not None:
        try:
            nouveau = seulement_bdt(charger_excel(up) if up.name.endswith("xlsx") else charger_csv(up.getvalue().decode("utf-8", errors="ignore"), est_texte=True))
            if nouveau and st.button(f"Remplacer ({len(nouveau)})", type="primary", disabled=not est_admin):
                st.session_state.ref = nouveau
                with open(os.path.join(DATA, "referentiel.csv"), "w", encoding="utf-8") as f:
                    f.write("code;isin;libelle;emetteur;categorie;nominal;taux_facial;jouissance;echeance;periodicite;amortissement;spread_bps\n")
                    for t in nouveau.values():
                        f.write(f"{t.code};{t.isin};{t.libelle};TRESOR;BDT;{t.nominal};{t.taux_facial};{t.jouissance};{t.echeance};1;In fine;0\n")
                _ref_defaut.clear(); st.success("Referentiel remplace."); st.rerun()
        except Exception as e:
            st.error(f"Fichier illisible : {e}")
    rech = st.text_input("Rechercher")
    df = pd.DataFrame([dict(Code=t.code, ISIN=t.isin, Libelle=t.libelle, Nominal=t.nominal, **{"Taux facial": pct(t.taux_facial, 2)}, Jouissance=fdate(t.jouissance), Echeance=fdate(t.echeance), **{"Residuel (ans)": round((t.echeance - date_val).days / 365, 2)}) for t in sorted(ref.values(), key=lambda x: x.echeance)])
    if rech:
        df = df[df.apply(lambda r: rech.lower() in " ".join(map(str, r.values)).lower(), axis=1)]
    st.dataframe(df, hide_index=True, width="stretch", height=560)


def page_carnet():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>CARNET</span>&nbsp;&nbsp;<span style='color:#5E6675'>qui achete quoi, qui vend quoi</span>", unsafe_allow_html=True)
    g, dr = st.columns([1.3, 1])
    with g:
        auteur = user["nom"]
        hist = st.session_state.setdefault("carnet_hist", [("bot", "Un ordre : « OPCVM Y achete 150 M du 14/05/2035 a 3,46 » · « Banque X vend 100 M du 5 ans, 2 ans a 2,55 et 5 ans a 3,02 » · « Assurance W achete du 5 ans » puis « aucune ». Une question : « qui vend du 20 ans cette semaine ? », « resume du jour ». « annule », « corrige : 100 M ».")])
        for role, txt in hist[-14:]:
            with st.chat_message("assistant" if role == "bot" else "user"):
                st.write(txt)
        msg = st.chat_input("Ecrire ici", disabled=not peut_ecrire)
        if msg:
            hist.append(("moi", msg))
            flux = store.flux(); low = msg.strip().lower()
            if low in ("aide", "?", "help"):
                rep = "Un ordre : qui, achete ou vend, la ligne (code, echeance ou « du 2035 »), le nominal, le taux. Une question : « qui achete du 10 ans ? », « resume de la semaine ». « annule » : retire le dernier ordre. « corrige : 100 M » ou « corrige : 3,5 » : modifie le dernier ordre."
            elif low.startswith("annule"):
                miens = [f for f in flux if f.get("auteur") == auteur] or flux
                if miens:
                    der = miens[-1]; flux = [f for f in flux if f["id"] != der["id"]]; store.enregistrer_flux(flux)
                    rep = "Retire : " + phrase_ordre(dict(contrepartie=der["contrepartie"], sens=der["sens"], code=der["code"], nominal=float(der["nominal"] or 0), taux=float(der["taux"]) if der.get("taux") else None), ref)
                else:
                    rep = "Rien a retirer."
            elif low.startswith("corrige"):
                miens = [f for f in flux if f.get("auteur") == auteur] or flux
                if miens:
                    der = miens[-1]
                    from pricer.carnet import lire_nominal, lire_taux
                    nom, _ = lire_nominal(msg); tx, _ = lire_taux(msg)
                    if nom: der["nominal"] = f"{nom:.0f}"
                    if tx: der["taux"] = f"{tx:.6f}"
                    if not nom and not tx:
                        m = __import__("re").search(r"(\d{1,2}[.,]\d{1,3})", msg)
                        if m: der["taux"] = f"{float(m.group(1).replace(',', '.'))/100:.6f}"
                    store.enregistrer_flux(flux)
                    rep = "Corrige : " + phrase_ordre(dict(contrepartie=der["contrepartie"], sens=der["sens"], code=der["code"], nominal=float(der["nominal"] or 0), taux=float(der["taux"]) if der.get("taux") else None), ref)
                else:
                    rep = "Rien a corriger."
            else:
                rep = requete(msg, flux, ref, dt.date.today())
                if rep is None:
                    o = comprendre(msg, ref, store.contacts(), dt.date.today(), st.session_state.get("ordre_en_cours"))
                    if o["complet"]:
                        nid = str(max([int(f["id"]) for f in flux if f.get("id", "").isdigit()] + [0]) + 1)
                        flux.append(dict(id=nid, date=o["date"].isoformat(), heure=dt.datetime.now().strftime("%H:%M"), auteur=auteur, contrepartie=o["contrepartie"], sens=o["sens"], code=o["code"],
                                         tenor=f"{o['tenor']:g}" if o.get("tenor") else "", nominal=f"{o['nominal']:.0f}", taux=f"{o['taux']:.6f}" if o.get("taux") else "", prix=f"{o['prix']:.4f}" if o.get("prix") else "",
                                         mode=o.get("mode", ""), cotations=" ; ".join(f"{k:g} ans {v*100:.3f}" for k, v in o.get("cotations", {}).items()), texte=msg, actif="1"))
                        store.enregistrer_flux(flux); st.session_state.ordre_en_cours = None
                        rep = "Note : " + phrase_ordre(o, ref)
                    else:
                        st.session_state.ordre_en_cours = o
                        rep = o["question"]
            hist.append(("bot", rep)); st.rerun()
    with dr:
        ong = st.tabs(["Matchs", "Ordres", "Aujourd'hui", "Radar"])
        auj = dt.date.today(); tout = store.flux()
        with ong[3]:
            c1, c2, c3 = st.columns(3)
            ps = c1.radio("Je cherche", ["Achat", "Vente"], horizontal=True, format_func=lambda x: "des acheteurs" if x == "Achat" else "des vendeurs")
            pt = c2.selectbox("Tenor", ["2 ans", "5 ans", "10 ans", "15 ans", "20 ans", "30 ans", "13s", "26s", "52s"]); pn = c3.number_input("MMAD", value=100, step=10)
            tv = {"13s": 0.25, "26s": 0.5, "52s": 1, "2 ans": 2, "5 ans": 5, "10 ans": 10, "15 ans": 15, "20 ans": 20, "30 ans": 30}[pt]
            qui = placer(tout, ref, auj, ps, tv, pn * 1e6)
            if qui:
                st.dataframe(pd.DataFrame([dict(Appeler=q["client"], Score=q["score"], **{"Dispo (MMAD)": round(q["disponible"] / 1e6), "Pourquoi": q["raisons"]}) for q in qui]), hide_index=True, width="stretch")
            else:
                st.caption("Personne de connu sur ce tenor.")
            rd = radar(tout, ref, auj)
            if rd:
                st.dataframe(pd.DataFrame([dict(Client=r["client"], Profil=r["profil"], Ordres=r["ordres"], Valables=r["valables"], **{"Achats (MMAD)": round(r["achats"] / 1e6), "Ventes (MMAD)": round(r["ventes"] / 1e6), "Taille moy.": round(r["taille_moyenne"] / 1e6), "Tenors": r["tenors"], "Dernier": r["dernier"].strftime("%d/%m/%Y") if r["dernier"] else ""}) for r in rd]), hide_index=True, width="stretch")
        with ong[0]:
            hz = st.number_input("Horizon (jours)", value=7, min_value=1, max_value=30, step=1)
            mm = matchs(tout, ref, auj, hz)
            if mm:
                dfm = pd.DataFrame([dict(Verdict=m["verdict"], Acheteur=m["acheteur"], Vendeur=m["vendeur"], Nature=m["nature"], **{"Ligne achat": m["ligne_a"], "Ligne vente": m["ligne_v"], "MMAD": round(m["nominal"] / 1e6), "Taux achat": pct(m["taux_a"]) if m["taux_a"] else "", "Taux vente": pct(m["taux_v"]) if m["taux_v"] else "", "Ecart (pb)": round(m["ecart_pb"], 1) if m["ecart_pb"] is not None else None}) for m in mm])
                st.dataframe(dfm.style.map(lambda v: f"color:{VERT};font-weight:700" if v == "croisable" else (f"color:#E5541E" if v == "a negocier" else ""), subset=["Verdict"]), hide_index=True, width="stretch")
            else:
                st.caption("Aucun croisement.")
        with ong[1]:
            clients = sorted({f["contrepartie"] for f in tout if f.get("contrepartie")})
            c1, c2 = st.columns(2)
            fc = c1.multiselect("Client", clients); fs = c2.selectbox("Sens", ["", "Achat", "Vente"])
            c1, c2 = st.columns(2)
            fd0 = c1.date_input("Du", value=auj - dt.timedelta(days=90), format="DD/MM/YYYY", key="fd0"); fd1 = c2.date_input("Au", value=auj, format="DD/MM/YYYY", key="fd1")
            c1, c2, c3 = st.columns(3)
            ft = c1.selectbox("Tenor", ["", "13s", "26s", "52s", "2 ans", "5 ans", "10 ans", "15 ans", "20 ans", "30 ans"]); fl = c2.text_input("Ligne (code, echeance, libelle)"); fv = c3.checkbox("Valables seulement")
            ten_val = {"13s": 0.25, "26s": 0.5, "52s": 1, "2 ans": 2, "5 ans": 5, "10 ans": 10, "15 ans": 15, "20 ans": 20, "30 ans": 30}.get(ft)
            sel = rechercher(tout, ref, auj, fc or None, fd0, fd1, ten_val, fl, fs or None, fv)
            if sel:
                dfo = pd.DataFrame([dict(id=f["id"], Valable=valable(f, auj), Date=f["date"], Client=f["contrepartie"], Sens=f["sens"], Ligne=f["code"] or (f"interet {f['tenor']} ans" if f.get("tenor") else ""), Echeance=fdate(ref[f["code"]].echeance) if f["code"] in ref else "", **{"MMAD": round(float(f["nominal"] or 0) / 1e6), "Taux": pct(float(f["taux"])) if f.get("taux") else "", "Mode": f.get("mode", ""), "Par": f.get("auteur", "")}) for f in sel])
                ed = st.data_editor(dfo, hide_index=True, width="stretch", key="edflux", disabled=[c for c in dfo.columns if c != "Valable"], column_config={"Valable": st.column_config.CheckboxColumn("Valable"), "id": None})
                if st.button("Enregistrer les validites", disabled=not peut_ecrire):
                    etat = {str(r["id"]): r["Valable"] for _, r in ed.iterrows()}
                    for f in tout:
                        if f["id"] in etat:
                            f["actif"] = "1" if etat[f["id"]] else "0"
                    store.enregistrer_flux(tout); st.rerun()
                st.caption(f"{len(sel)} ordre(s) · un ordre de plus de 30 jours n'est plus valable.")
                st.download_button("Exporter", excel_bytes({"Ordres": pd.DataFrame(sel)}), "ordres.xlsx")
            else:
                st.caption("Aucun ordre.")
        with ong[2]:
            fx = [f for f in tout if f.get("date") == auj.isoformat()]
            if fx:
                df = pd.DataFrame([dict(Heure=f["heure"], Qui=f["contrepartie"], Sens=f["sens"], Ligne=f["code"] or (f"interet {f['tenor']} ans" if f.get("tenor") else ""), **{"MMAD": round(float(f["nominal"] or 0) / 1e6), "Taux": pct(float(f["taux"])) if f.get("taux") else "", "Mode": f.get("mode", "")}) for f in fx])
                st.dataframe(df, hide_index=True, width="stretch")
                ach = sum(float(f["nominal"] or 0) for f in fx if f["sens"] == "Achat") / 1e6; ven = sum(float(f["nominal"] or 0) for f in fx if f["sens"] == "Vente") / 1e6
                k = st.columns(3); k[0].metric("Achats", mnt(ach)); k[1].metric("Ventes", mnt(ven)); k[2].metric("Net", mnt(ach - ven))
            else:
                st.caption("Rien aujourd'hui.")


def atelier_simulateur():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>SIMULATEUR</span>&nbsp;&nbsp;<span style='color:#5E6675'>et si · courbe a la main · horizon</span>", unsafe_allow_html=True)
    if not courbe:
        st.warning("Aucune courbe."); return
    g = {"nominal": [tuple(x) for x in par["limites_nominal"]], "sensi": [tuple(x) for x in par["limites_sensi"]]}
    pos0, base = store.positions_a(date_val, ref, base_pos)
    z1, z2, z3 = st.columns([0.85, 1.05, 1.35], gap="medium")
    # ------------------------------------------------ 1 contexte
    with z1:
        zone("1 · CONTEXTE")
        e0 = evaluer(pos0, ref, courbe, date_val, methode, g); a0 = e0["agregats"]
        st.caption(f"{fdate(date_val)} · {courbe.source[:40]} · photo du {fdate(base) if base else '-'}")
        k = st.columns(2); k[0].metric("Valeur (MMAD)", mnt(a0["valeur_marche"] / 1e6, 1)); k[1].metric("PVBP (MAD/pb)", mnt(a0["pvbp"]))
        k = st.columns(2); k[0].metric("Duration", num(a0["duration"], 2)); k[1].metric("Lignes", str(a0["nb"]))
        k0 = krd(pos0, ref, courbe, date_val)
        st.caption("Sensibilite par tenor, MAD/pb")
        dk = pd.DataFrame({"Tenor": [x["tenor"].replace("semaines", "s") for x in k0], "PVBP": [x["pvbp"] for x in k0]})
        st.altair_chart(alt.Chart(dk).mark_bar(color=BLEU).encode(x=alt.X("Tenor", sort=None, title=None), y=alt.Y("PVBP", title=None)).properties(height=180), width="stretch")
        statuts = [x["statut"] for x in e0["limites"]]
        st.caption(f"Limites : {statuts.count('DEPASSEMENT')} depassement, {statuts.count('Vigilance')} vigilance")
    # ------------------------------------------------ 2 travail
    with z2:
        zone("2 · TRAVAIL")
        ong = st.tabs(["Et si", "Courbe a la main", "Horizon"])
        with ong[0]:
            if "sim_ops" not in st.session_state:
                st.session_state.sim_ops = pd.DataFrame([{"sens": "Achat", "code": st.session_state.get("dernier_titre", "201898"), "nominal": 100_000_000}])
            ed = st.data_editor(st.session_state.sim_ops, num_rows="dynamic", width="stretch", key="sim_ed",
                                column_config={"sens": st.column_config.SelectboxColumn("Sens", options=["Achat", "Vente"]), "code": st.column_config.TextColumn("Code"), "nominal": st.column_config.NumberColumn("Nominal (MAD)", step=1_000_000, format="%d")})
            st.session_state.sim_ops = ed
            ops = [dict(sens=r["sens"], code=str(r["code"]).strip(), nominal=r["nominal"]) for _, r in ed.iterrows() if str(r.get("code", "")).strip() in ref and pd.notna(r.get("nominal")) and r["nominal"]]
            inconnus = [str(r["code"]) for _, r in ed.iterrows() if str(r.get("code", "")).strip() not in ("", "nan") and str(r["code"]).strip() not in ref]
            if inconnus: st.warning("Codes inconnus : " + ", ".join(inconnus))
            if st.button("Vider"):
                st.session_state.sim_ops = pd.DataFrame(columns=["sens", "code", "nominal"]); st.rerun()
        with ong[1]:
            if "sim_chocs" not in st.session_state:
                st.session_state.sim_chocs = [0] * 9
            def _preset(vals):
                st.session_state.sim_chocs = list(vals)
                for k in range(9):
                    st.session_state[f"sl{k}"] = int(vals[k])
                st.rerun()
            c1, c2, c3, c4, c5 = st.columns(5)
            if c1.button("+25 //"): _preset([25] * 9)
            if c2.button("-25 //"): _preset([-25] * 9)
            if c3.button("Pente +"): _preset([0, 0, 0, 0, 10, 25, 25, 25, 25])
            if c4.button("Aplat."): _preset([0, 0, 0, 0, -10, -25, -25, -25, -25])
            if c5.button("Plat"): _preset([0] * 9)
            chocs = []
            for k in range(9):
                chocs.append(st.slider(TENORS[k][0], -100, 100, int(st.session_state.sim_chocs[k]), 1, key=f"sl{k}"))
            st.session_state.sim_chocs = chocs
            cs = deformer(courbe, chocs, date_val)
            st.line_chart(pd.DataFrame({"Maturite": [j / 365 for _, j, _ in TENORS], "Courbe (%)": [x * 100 for x in courbe.actuariels()], "Simulee (%)": [x * 100 for x in cs.actuariels()]}).set_index("Maturite"), height=200)
        with ong[2]:
            dh = st.date_input("Horizon", value=date_val + dt.timedelta(days=91), min_value=date_val + dt.timedelta(days=1), format="DD/MM/YYYY", key="sim_h")
            tf = st.number_input("Financement (%)", value=float(par["taux_financement"] * 100), step=0.05, format="%.2f", key="sim_tf") / 100
        chocs = st.session_state.sim_chocs; cs = deformer(courbe, chocs, date_val); choque = any(chocs)
    # ------------------------------------------------ 3 resultat
    with z3:
        zone("3 · RESULTAT")
        pos1 = appliquer_operations(pos0, ops, ref)
        e1 = evaluer(pos1, ref, cs, date_val, methode, g); a1 = e1["agregats"]
        e0s = evaluer(pos0, ref, cs, date_val, methode, g)
        lab = ("portefeuille actuel", "simule" + (" (ops" if ops else "") + (" + courbe)" if (ops and choque) else (")" if ops else (" (courbe)" if choque else ""))))
        rows = [("Valeur de marche", a0["valeur_marche"], a1["valeur_marche"], 0), ("Nominal", a0["nominal"], a1["nominal"], 0), ("Sensibilite", a0["sensi"], a1["sensi"], 3), ("Duration", a0["duration"], a1["duration"], 3),
                ("PVBP", a0["pvbp"], a1["pvbp"], 0), ("Convexite", a0["convexite"], a1["convexite"], 1), ("Sensi nominale", a0["sensi_nominale"], a1["sensi_nominale"], 0), ("Lignes", a0["nb"], a1["nb"], 0)]
        st.dataframe(pd.DataFrame([{"": r[0], lab[0]: mnt(r[1], r[3]), lab[1]: mnt(r[2], r[3]), "Delta": mnt(r[2] - r[1], r[3])} for r in rows]).set_index(""), width="stretch")
        cash = sum((-1 if o["sens"] == "Achat" else 1) * next((l.valeur_marche for l in evaluer({o["code"]: [o["nominal"] / ref[o["code"]].nominal, ""]}, ref, courbe, date_val, methode, g)["lignes"]), 0) for o in ops)
        k = st.columns(3)
        k[0].metric("Effet courbe immediat (MAD)", mnt(e0s["agregats"]["valeur_marche"] - a0["valeur_marche"]), help="portefeuille actuel reevalue sur la courbe simulee")
        k[1].metric("Cash des operations (MAD)", mnt(cash)); k[2].metric("Effet courbe, portefeuille simule", mnt(a1["valeur_marche"] - evaluer(pos1, ref, courbe, date_val, methode, g)["agregats"]["valeur_marche"]))
        tabs = st.tabs(["Limites", "Horizon", "Scenarios", "VaR", "Par ligne", "Tenors", "Couverture"])
        with tabs[0]:
            st.dataframe(pd.DataFrame([dict(Palier=x0["palier"], Avant=pct(x0["utilisation"], 0), Apres=pct(x1["utilisation"], 0), Statut=x1["statut"], Restant=mnt(x1["restant"])) for x0, x1 in zip(e0["limites"], e1["limites"])]).style.map(lambda v: f"color:{ROUGE};font-weight:700" if v == "DEPASSEMENT" else ("color:#E5541E;font-weight:700" if v == "Vigilance" else f"color:{VERT}"), subset=["Statut"]), hide_index=True, width="stretch")
        with tabs[1]:
            h0 = pnl_horizon(pos0, ref, courbe, cs, date_val, dh, methode, tf); h1 = pnl_horizon(pos1, ref, courbe, cs, date_val, dh, methode, tf)
            st.caption(f"{h0['jours']} jours · courbe d'horizon = courbe simulee · carry = couru + coupons ; temps = roll-down ; courbe = chocs ; financement")
            st.dataframe(pd.DataFrame([{"": k2, lab[0]: mnt(h0[k3]), lab[1]: mnt(h1[k3]), "Delta": mnt(h1[k3] - h0[k3])} for k2, k3 in (("Carry", "carry"), ("Temps", "roll"), ("Courbe", "courbe"), ("Financement", "financement"), ("P&L total", "total"))]).set_index(""), width="stretch")
        with tabs[2]:
            s0 = scenarios_sim(pos0, ref, courbe, date_val, methode); s1 = scenarios_sim(pos1, ref, courbe, date_val, methode)
            dsc = pd.DataFrame([{"Scenario": a["scenario"], lab[0]: round(a["pnl"]), lab[1]: round(b["pnl"]), "Delta": round(b["pnl"] - a["pnl"])} for a, b in zip(s0, s1)])
            st.dataframe(dsc.style.map(rouge_vert, subset=[lab[0], lab[1]]), hide_index=True, width="stretch")
            pire0 = min(s0, key=lambda x: x["pnl"]); pire1 = min(s1, key=lambda x: x["pnl"])
            st.caption(f"Pire scenario : {pire0['scenario']} {mnt(pire0['pnl'])} → {pire1['scenario']} {mnt(pire1['pnl'])}")
        with tabs[3]:
            v0 = var_historique(pos0, ref, courbe, date_val, courbes_dispo, methode); v1 = var_historique(pos1, ref, courbe, date_val, courbes_dispo, methode)
            if v0["ok"]:
                st.dataframe(pd.DataFrame([{"": k2, lab[0]: mnt(v0[k3]), lab[1]: mnt(v1[k3])} for k2, k3 in (("Pire variation observee", "pire"), ("VaR 95 %", "var95"), ("VaR 99 %", "var99"), ("Moyenne", "moyenne"), ("Meilleure", "meilleur"))]).set_index(""), width="stretch")
                st.caption(f"{v0['n']} variations de courbe observees dans l'historique, appliquees a la courbe du jour. Plus l'historique est long, plus la VaR est parlante.")
            else:
                st.caption(v0["message"])
        with tabs[4]:
            d0 = {l.code: l for l in e0["lignes"]}; d1 = {l.code: l for l in e1["lignes"]}
            rows2 = []
            for c in sorted(set(d0) | set(d1), key=lambda c: ref[c].echeance if c in ref else dt.date.max):
                v_av = d0[c].valeur_marche if c in d0 else 0; v_ap = d1[c].valeur_marche if c in d1 else 0
                imm = (evaluer({c: pos0[c]}, ref, cs, date_val, methode, g)["agregats"]["valeur_marche"] - v_av) if (c in pos0 and choque) else 0
                rows2.append({"Code": c, "Libelle": ref[c].libelle if c in ref else "", "Avant": round(v_av), "Apres": round(v_ap), "Delta valeur": round(v_ap - v_av), "Effet courbe": round(imm), "PVBP avant": round(d0[c].pvbp) if c in d0 else 0, "PVBP apres": round(d1[c].pvbp) if c in d1 else 0})
            st.dataframe(pd.DataFrame(rows2).style.map(rouge_vert, subset=["Delta valeur", "Effet courbe"]), hide_index=True, width="stretch")
        with tabs[5]:
            k1 = krd(pos1, ref, courbe, date_val)
            dk2 = pd.DataFrame([dict(Tenor=x["tenor"].replace("semaines", "s"), Portefeuille=lab[0], PVBP=x["pvbp"]) for x in k0] + [dict(Tenor=x["tenor"].replace("semaines", "s"), Portefeuille=lab[1], PVBP=x["pvbp"]) for x in k1])
            st.altair_chart(alt.Chart(dk2).mark_bar().encode(x=alt.X("Tenor", sort=None, title=None), y=alt.Y("PVBP", title=None), color=alt.Color("Portefeuille", scale=alt.Scale(range=[BLEU, ROUGE]), legend=alt.Legend(title=None, orient="top")), xOffset="Portefeuille").properties(height=220), width="stretch")
        with tabs[6]:
            ct = st.selectbox("Neutraliser le tenor", list(range(9)), format_func=lambda i: TENORS[i][0], index=4)
            cands = [k2 for k2 in sorted(ref, key=lambda k2: ref[k2].echeance) if ref[k2].echeance > date_val and abs((ref[k2].echeance - date_val).days - JOURS_T[ct]) < JOURS_T[ct] * 0.6 + 200]
            sel = st.multiselect("Avec", cands, default=cands[-2:], format_func=lambda k2: f"{k2} - {ref[k2].libelle}")
            if sel:
                cv = couverture(pos1, ref, courbe, date_val, ct, sel)
                st.dataframe(pd.DataFrame([dict(Code=x["code"], Libelle=x["libelle"], Sens=x["sens"], **{"Nominal (MMAD)": round(abs(x["nominal"]) / 1e6, 1), "PVBP par titre": round(x["pvbp_titre"], 2)}) for x in cv]), hide_index=True, width="stretch")
                st.caption("Nominal qui ramene a zero la sensibilite du tenor choisi, apres les operations « et si ».")
        st.download_button("Exporter la simulation", excel_bytes({"Avant": pd.DataFrame([vars(l) for l in e0["lignes"]]), "Apres": pd.DataFrame([vars(l) for l in e1["lignes"]]), "Scenarios": dsc, "Operations": pd.DataFrame(ops)}), "simulation.xlsx")


JOURS_T = [j for _, j, _ in TENORS]


def atelier_qualifier():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>QUALIFIER</span>&nbsp;&nbsp;<span style='color:#5E6675'>intermediation · compte propre · eBond · swap · primaire</span>", unsafe_allow_html=True)
    g, dr = st.columns([1, 2])
    with g:
        src = st.radio("Operations", ["Journal", "Fichier"], horizontal=True)
        delai = st.number_input("Delai max entre les deux jambes (jours)", value=5, min_value=0, max_value=30)
        ops = store.operations()
        if src == "Fichier":
            up = st.file_uploader("Fichier (canevas operations)", type=["xlsx", "csv"], key="qual_up")
            if up is not None:
                try:
                    dfu = pd.read_excel(up) if up.name.endswith("xlsx") else pd.read_csv(up, sep=None, engine="python"); dfu.columns = [str(c).strip().lower() for c in dfu.columns]
                    ops = []
                    for i2, r in dfu.iterrows():
                        ops.append(dict(id=str(i2 + 1), date=pd.to_datetime(r["date"]).date().isoformat(), date_valeur=pd.to_datetime(r["date_valeur"]).date().isoformat() if pd.notna(r.get("date_valeur")) and r.get("date_valeur") not in ("", None) else "", sens="Achat" if str(r.get("sens", "")).lower().startswith("a") else "Vente",
                                        code=str(r.get("code", "")).strip(), nominal=str(r.get("nominal", "") or ""), prix_plein=str(r.get("prix_plein", "") or ""), taux=str(r.get("taux", "") or ""), contrepartie=str(r.get("contrepartie", "") or ""), client=str(r.get("client", "") or ""),
                                        fonds="", parent_id="", intermediation_id="", canal=str(r.get("canal", "Marche") or "Marche"), nature="", commentaire=str(r.get("commentaire", "") or ""), saisie_le=""))
                except Exception as e:
                    st.error(f"Fichier illisible : {e}"); ops = []
        st.caption("Regles : intermediation = achat puis vente du meme titre, meme nominal, contreparties differentes, sous le delai ; swap = achat et vente le meme jour avec la meme contrepartie sur deux titres ; primaire pour contrepartie = achat en primaire puis vente du meme titre a un tiers ; eBond et primaire d'apres le canal ; le reste est compte propre.")
    q = qualifier(ops, ref, int(delai)) if ops else []
    with dr:
        if not q:
            st.info("Aucune operation."); return
        rs = resume_qualif(q)
        st.dataframe(pd.DataFrame([dict(Nature=x["nature"], Operations=x["nb"], **{"Achats (MAD)": mnt(x["achats"]), "Ventes (MAD)": mnt(x["ventes"])}) for x in rs]), hide_index=True, width="stretch")
        rows = []
        for o in sorted(q, key=lambda o: (o["date"], o["id"])):
            lien = o.get("intermediation_id") or o.get("swap_id") or o.get("primaire_id") or (("↳ " + o["parent_id"]) if o.get("parent_id") else "")
            rows.append({"id": o["id"], "Nature": o.get("nature", ""), "Lien": lien, "Date": o["date"], "Sens": o["sens"], "Code": o["code"], "Libelle": ref[o["code"]].libelle if o["code"] in ref else "", "Nominal": mnt(float(o["nominal"])) if o.get("nominal") else "", "Prix": num(float(o["prix_plein"])) if o.get("prix_plein") else "", "Taux": pct(float(o["taux"])) if o.get("taux") else "", "Contrepartie": o.get("contrepartie", ""), "Client": o.get("client", ""), "Canal": o.get("canal", "")})
        dq = pd.DataFrame(rows)
        ed = st.data_editor(dq, hide_index=True, width="stretch", key="edqual", disabled=[c for c in dq.columns if c != "Nature"], column_config={"Nature": st.column_config.SelectboxColumn("Nature", options=NATURES + [n + " (ventilation)" for n in NATURES])})
        c1, c2 = st.columns(2)
        if src == "Journal" and c1.button("Appliquer au journal", type="primary", disabled=not peut_ecrire):
            nat = {str(r["id"]): r["Nature"] for _, r in ed.iterrows()}; liens = {o["id"]: o for o in q}
            tout = store.operations()
            for o in tout:
                if o["id"] in nat:
                    o["nature"] = nat[o["id"]]
                    qo = liens.get(o["id"], {})
                    if qo.get("intermediation_id") and not o.get("intermediation_id"): o["intermediation_id"] = qo["intermediation_id"]
            store.enregistrer_operations(tout); st.rerun()
        c2.download_button("Exporter", excel_bytes({"Qualification": ed, "Resume": pd.DataFrame(rs)}), "qualification.xlsx")


def atelier_prix_taux():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>PRIX ↔ TAUX</span>", unsafe_allow_html=True)
    z1, z2, z3 = st.columns([0.9, 1, 1], gap="medium")
    with z1:
        zone("1 · TITRE")
        d = st.date_input("Date", value=date_val, format="DD/MM/YYYY", key="pt_d")
        t = choisir_titre("pt", d)
        if not t:
            return
        qte = st.number_input("Quantite (titres)", value=100, min_value=1, step=10, key="pt_q")
        car = caracteristiques(t, d)
        st.caption(f"{fdate(t.echeance)} · coupon {pct(t.taux_facial, 2)} · residuel {car.residuel} j · {car.regime}")
        st.caption(f"Couru a cette date : {num(coupon_couru(t, d, car))} %")
    nominal = qte * t.nominal
    with z2:
        zone("2 · PRIX → TAUX")
        typ = st.radio("Prix saisi", ["Plein", "Pied"], horizontal=True, key="pt_typ")
        c = courbe_active(d); r_def = c.taux_pour(t.echeance, d, methode)[0] if c else t.taux_facial
        px = st.number_input("Prix (%)", value=float(round(prix_plein(t, d, r_def) - (coupon_couru(t, d, car) if typ == "Pied" else 0), 4)), step=0.01, format="%.4f", key="pt_px")
        r = taux_depuis_prix(t, d, px, plein=(typ == "Plein")); v = valoriser(t, d, r)
        big("TAUX", pct(r), True)
        st.table(pd.DataFrame({"": ["Prix plein", "Prix pied", "Coupon couru", "Montant plein (MAD)", "Sensibilite", "Duration"], "Valeur": [num(v.prix_plein) + " %", num(v.prix_pied) + " %", num(v.coupon_couru) + " %", mnt(nominal * v.prix_plein / 100, 2), num(v.sensi), num(v.duration, 3)]}).set_index(""))
    with z3:
        zone("3 · TAUX → PRIX")
        tx = st.number_input("Taux (%)", value=float(round(r_def * 100, 3)), step=0.001, format="%.3f", key="pt_tx")
        v2 = valoriser(t, d, tx / 100)
        big("PRIX PLEIN", num(v2.prix_plein) + " %"); big("PRIX PIED", num(v2.prix_pied) + " %")
        st.table(pd.DataFrame({"": ["Coupon couru", "Montant plein (MAD)", "Montant pied (MAD)", "Couru (MAD)", "Sensibilite", "Duration", "PVBP (MAD/pb)"], "Valeur": [num(v2.coupon_couru) + " %", mnt(nominal * v2.prix_plein / 100, 2), mnt(nominal * v2.prix_pied / 100, 2), mnt(nominal * v2.coupon_couru / 100, 2), num(v2.sensi), num(v2.duration, 3), mnt(v2.sensi * nominal * v2.prix_plein / 100 * 1e-4, 1)]}).set_index(""))
    st.subheader("En serie")
    st.caption("Une ligne par conversion : code, date, et soit le prix plein, soit le taux ; l'autre se calcule.")
    if "pt_serie" not in st.session_state:
        st.session_state.pt_serie = pd.DataFrame([dict(code=t.code, date=d, prix_plein=None, taux=round(r_def * 100, 3))])
    ed = st.data_editor(st.session_state.pt_serie, num_rows="dynamic", width="stretch", key="pt_ed", column_config={"code": st.column_config.TextColumn("Code"), "date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"), "prix_plein": st.column_config.NumberColumn("Prix plein (%)", format="%.4f"), "taux": st.column_config.NumberColumn("Taux (%)", format="%.3f")})
    st.session_state.pt_serie = ed
    rows = []
    for _, r_ in ed.iterrows():
        tt = ref.get(str(r_.get("code", "")).strip())
        if not tt or pd.isna(r_.get("date")): continue
        dd = pd.to_datetime(r_["date"]).date()
        if pd.notna(r_.get("prix_plein")) and r_.get("prix_plein") not in ("", None):
            rr = taux_depuis_prix(tt, dd, float(r_["prix_plein"])); vv = valoriser(tt, dd, rr); sens_ = "prix → taux"
        elif pd.notna(r_.get("taux")) and r_.get("taux") not in ("", None):
            rr = float(r_["taux"]) / 100; vv = valoriser(tt, dd, rr); sens_ = "taux → prix"
        else:
            continue
        rows.append({"Code": tt.code, "Libelle": tt.libelle, "Date": fdate(dd), "Sens": sens_, "Taux": pct(rr), "Prix plein": num(vv.prix_plein), "Prix pied": num(vv.prix_pied), "Couru": num(vv.coupon_couru), "Sensi": num(vv.sensi), "Duration": num(vv.duration, 3)})
    if rows:
        dfr = pd.DataFrame(rows); st.dataframe(dfr, hide_index=True, width="stretch")
        st.download_button("Exporter", excel_bytes({"Conversions": dfr}), "conversions.xlsx")


def page_resume():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>RÉSUMÉ</span>&nbsp;&nbsp;<span style='color:#5E6675'>le mail de 17 h</span>", unsafe_allow_html=True)
    dates = sorted(courbes_dispo)
    pnl = pnl_journalier(store, ref, dates[-2], dates[-1], methode, par["taux_financement"], base_pos) if len(dates) >= 2 else []
    objet, corps = resume_jour(store, ref, dt.date.today(), courbe, pnl, pct, mnt)
    dest = [x.strip() for x in str(par.get("resume_destinataires", "") if isinstance(par.get("resume_destinataires"), str) else ";".join(par.get("resume_destinataires", []))).replace(",", ";").split(";") if x.strip()]
    st.text_input("A", "; ".join(dest), key="r_a"); st.text_input("Objet", objet, key="r_obj"); st.text_area("Corps", corps, height=420, key="r_corps")
    lien = "mailto:" + ",".join(dest) + "?" + urllib.parse.urlencode({"subject": objet, "body": corps}, quote_via=urllib.parse.quote)
    c1, c2 = st.columns(2)
    c1.link_button("Ouvrir le mail", lien, type="primary"); c2.download_button("Enregistrer (.txt)", corps.encode("utf-8"), f"resume_{dt.date.today().isoformat()}.txt")
    st.caption("Envoi automatique a 17 h : planifier `python resume_17h.py` (SMTP et destinataires dans Parametres).")


TYPES_TIERS = ["SDG", "Fonds", "Banque", "Assurance", "CDG", "Depositaire", "Autre"]


def tiers_par_nom():
    return {t["nom"]: t for t in store.tiers() if t.get("nom")}


def emails_de(nom: str, role: str = "A") -> list:
    return [x["email"] for x in store.contacts() if x.get("contrepartie") == nom and x.get("email") and str(x.get("role", "A")).upper().startswith(role[0].upper())]


def page_contacts():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>CONTACTS</span>", unsafe_allow_html=True)
    g, dr = st.columns(2)
    with g:
        st.subheader("Tiers")
        st.caption("Une SDG a des fonds ; chaque fonds a son depositaire.")
        dft = pd.DataFrame(store.tiers()) if store.tiers() else pd.DataFrame(columns=["nom", "type", "parent", "depositaire"])
        noms = [t["nom"] for t in store.tiers() if t.get("nom")]
        edt = st.data_editor(dft, num_rows="dynamic", width="stretch", key="edtiers", column_config={"nom": st.column_config.TextColumn("Nom"), "type": st.column_config.SelectboxColumn("Type", options=TYPES_TIERS), "parent": st.column_config.TextColumn("SDG (pour un fonds)"), "depositaire": st.column_config.TextColumn("Depositaire")})
        if st.button("Enregistrer les tiers", type="primary"):
            store.enregistrer_tiers([dict(nom=str(r["nom"]).strip(), type=str(r.get("type", "Autre") or "Autre"), parent=str(r.get("parent", "") or "").strip(), depositaire=str(r.get("depositaire", "") or "").strip()) for _, r in edt.iterrows() if str(r.get("nom", "")).strip() not in ("", "nan")])
            st.rerun()
    with dr:
        st.subheader("E-mails")
        df = pd.DataFrame(store.contacts()) if store.contacts() else pd.DataFrame(columns=["contrepartie", "nom", "email", "role"])
        ed = st.data_editor(df, num_rows="dynamic", width="stretch", key="edcontacts",
                            column_config={"contrepartie": st.column_config.SelectboxColumn("Tiers", options=noms) if noms else st.column_config.TextColumn("Tiers"), "nom": st.column_config.TextColumn("Nom"), "email": st.column_config.TextColumn("E-mail"), "role": st.column_config.SelectboxColumn("Role", options=["A", "Cc"])})
        if st.button("Enregistrer les e-mails", type="primary"):
            store.enregistrer_contacts([dict(contrepartie=str(r["contrepartie"]).strip(), nom=str(r.get("nom", "") or ""), email=str(r.get("email", "") or "").strip(), role=str(r.get("role", "A") or "A")) for _, r in ed.iterrows() if str(r.get("contrepartie", "")).strip() not in ("", "nan")])
            st.rerun()
    st.download_button("Canevas", excel_bytes({"Tiers": pd.DataFrame([dict(nom="SDG Alpha", type="SDG", parent="", depositaire=""), dict(nom="Fonds A", type="Fonds", parent="SDG Alpha", depositaire="Depositaire Z"), dict(nom="Banque X", type="Banque", parent="", depositaire="")]), "Emails": pd.DataFrame([dict(contrepartie="Banque X", nom="Prenom Nom", email="trading@banquex.ma", role="A")])}), "canevas_contacts.xlsx")


def page_parametres():
    st.markdown("<span style='font-size:1.1rem;font-weight:700;letter-spacing:.25em;color:#C9285A'>PARAMÈTRES</span>", unsafe_allow_html=True)
    p = dict(par)
    p["taux_financement"] = st.number_input("Financement (%)", value=float(p["taux_financement"] * 100), step=0.05, format="%.2f") / 100
    p["methode_defaut"] = st.radio("Lecture par defaut", ["lignes", "tenors"], index=0 if p["methode_defaut"] == "lignes" else 1, format_func=lambda m: "Lignes" if m == "lignes" else "Tenors", horizontal=True)
    p["regle_ebond"] = st.radio("Courbe du jour", list(REGLES), index=list(REGLES).index(p.get("regle_ebond", "lignes")), format_func=lambda k: {"bkam": "BKAM seule", "lignes": "Lignes eBond", "decalage": "Decalage"}[k], horizontal=True)
    st.subheader("Resume de 17 h")
    p["resume_destinataires"] = [x.strip() for x in st.text_input("Destinataires (separes par ;)", ";".join(p.get("resume_destinataires", []))).split(";") if x.strip()]
    sm = p.get("smtp") or {}
    c1, c2, c3, c4 = st.columns(4)
    sm["hote"] = c1.text_input("SMTP hote", sm.get("hote", "")); sm["port"] = c2.text_input("Port", str(sm.get("port", 587))); sm["utilisateur"] = c3.text_input("Utilisateur", sm.get("utilisateur", "")); sm["mot_de_passe"] = c4.text_input("Mot de passe SMTP", sm.get("mot_de_passe", ""), type="password")
    sm["expediteur"] = sm.get("utilisateur", "")
    p["smtp"] = sm if sm.get("hote") else None
    st.subheader("Limites")
    a, b = st.columns(2)
    with a:
        dn = st.data_editor(pd.DataFrame(p["limites_nominal"], columns=["Palier", "Seuil (ans)", "Limite (MAD)"]), hide_index=True, width="stretch", key="ln")
    with b:
        ds = st.data_editor(pd.DataFrame(p["limites_sensi"], columns=["Palier", "Seuil (ans)", "Limite (MAD/pb)"]), hide_index=True, width="stretch", key="ls")
    if st.button("Enregistrer", type="primary", disabled=not est_admin):
        p["limites_nominal"] = dn.values.tolist(); p["limites_sensi"] = ds.values.tolist()
        store.enregistrer_parametres(p); st.rerun()
    st.subheader("Mon mot de passe")
    with st.form("mdp"):
        n1 = st.text_input("Nouveau", type="password"); n2 = st.text_input("Confirmer", type="password")
        if st.form_submit_button("Changer"):
            if n1 and n1 == n2:
                usagers.mot_de_passe(user["login"], n1); st.success("Change.")
            else:
                st.error("Les deux saisies different.")
    if est_admin:
        st.subheader("Utilisateurs")
        dfu = pd.DataFrame([dict(Identifiant=r["login"], Nom=r["nom"], Actif=r.get("actif", "1") == "1", Cree=r.get("cree_le", "")) for r in usagers.lire()])
        st.dataframe(dfu, hide_index=True, width="stretch")
        with st.form("nouvel_utilisateur"):
            c1, c2, c3 = st.columns(3)
            lg = c1.text_input("Identifiant"); nm = c2.text_input("Nom"); mp = c3.text_input("Mot de passe", type="password")
            if st.form_submit_button("Ajouter ou mettre a jour"):
                if lg and nm and mp:
                    usagers.ajouter(lg, nm, "admin", mp); st.rerun()
        c1, c2 = st.columns(2)
        cible = c1.selectbox("Utilisateur", [r["login"] for r in usagers.lire()])
        if c2.button("Activer / desactiver"):
            u = next(r for r in usagers.lire() if r["login"] == cible)
            usagers.desactiver(cible, u.get("actif", "1") != "1"); st.rerun()


{"COTER": atelier_coter, "OPÉRER": page_operations, "PORTEFEUILLE": page_portefeuille, "P&L": page_pnl, "SWAPPER": page_swap,
 "PRIX ↔ TAUX": atelier_prix_taux, "QUALIFIER": atelier_qualifier, "SIMULATEUR": atelier_simulateur, "CARNET": page_carnet, "COURBE": page_courbe, "RÉSUMÉ": page_resume, "CONTACTS": page_contacts, "RÉFÉRENTIEL": page_referentiel, "PARAMÈTRES": page_parametres}[page]()
