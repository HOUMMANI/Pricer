"""Simulateur de swap de titres entre salles : mes lignes contre les lignes de la contrepartie."""
from __future__ import annotations
import datetime as dt
from .bdt import valoriser


def _jambe(lignes: list, ref: dict, courbe, d: dt.date, methode: str) -> list:
    out = []
    for code, nominal in lignes:
        t = ref.get(str(code).strip())
        if not t or nominal <= 0:
            continue
        r, note = courbe.taux_pour(t.echeance, d, methode)
        v = valoriser(t, d, r)
        vm = nominal * v.prix_plein / 100
        out.append(dict(code=t.code, libelle=t.libelle, echeance=t.echeance, maturite=(t.echeance - d).days / 365, nominal=nominal, taux=r,
                        prix_plein=v.prix_plein, prix_pied=v.prix_pied, couru=nominal * v.coupon_couru / 100, valeur=vm, sensi=v.sensi,
                        pvbp=v.sensi * vm * 1e-4, sensi_nominale=nominal * v.sensi / 1e4, duration=v.duration))
    return out


def simuler(mes_lignes: list, lignes_cp: list, ref: dict, courbe_aller, courbe_retour, d_aller: dt.date, d_retour: dt.date,
            mode: str, volume: float, methode: str, taux_fin: float = 0.0) -> dict:
    """mes_lignes : [(code, poids)] ; lignes_cp : [(code, poids)]. Les poids repartissent le volume (nominal total) sur les jambes.
    mode : 'volume' (meme nominal des deux cotes) ou 'sensi' (nominal de la contrepartie ajuste pour egaliser les PVBP a l aller)."""
    def repartir(lst, total):
        s = sum(w for _, w in lst) or 1
        return [(c, total * w / s) for c, w in lst]
    mes = _jambe(repartir(mes_lignes, volume), ref, courbe_aller, d_aller, methode)
    if not mes:
        return dict(ok=False, message="aucune de mes lignes n est valorisable")
    cp = _jambe(repartir(lignes_cp, volume), ref, courbe_aller, d_aller, methode)
    if not cp:
        return dict(ok=False, message="aucune ligne de contrepartie valorisable")
    if mode == "sensi":
        pv_m, pv_c = sum(x["pvbp"] for x in mes), sum(x["pvbp"] for x in cp)
        if pv_c > 0:
            k = pv_m / pv_c
            cp = _jambe([(x["code"], x["nominal"] * k) for x in cp], ref, courbe_aller, d_aller, methode)
    # retour : memes nominaux, courbe de la date retour
    mes_r = _jambe([(x["code"], x["nominal"]) for x in mes], ref, courbe_retour, d_retour, methode)
    cp_r = _jambe([(x["code"], x["nominal"]) for x in cp], ref, courbe_retour, d_retour, methode)
    som = lambda lst, k: sum(x[k] for x in lst)
    jours = (d_retour - d_aller).days
    soulte = som(cp, "valeur") - som(mes, "valeur")              # ce que je paie (si > 0) pour recevoir leurs titres
    # P&L pour moi : je detiens leurs titres pendant la periode au lieu des miens
    carry_recu = som(cp_r, "couru") - som(cp, "couru"); carry_donne = som(mes_r, "couru") - som(mes, "couru")
    mtm_recu = som(cp_r, "valeur") - som(cp, "valeur"); mtm_donne = som(mes_r, "valeur") - som(mes, "valeur")
    fin = -soulte * taux_fin * jours / 360
    return dict(ok=True, mes=mes, cp=cp, mes_retour=mes_r, cp_retour=cp_r, jours=jours, soulte=soulte,
                pvbp_mes=som(mes, "pvbp"), pvbp_cp=som(cp, "pvbp"), nominal_mes=som(mes, "nominal"), nominal_cp=som(cp, "nominal"),
                carry_recu=carry_recu, carry_donne=carry_donne, carry_net=carry_recu - carry_donne,
                mtm_recu=mtm_recu, mtm_donne=mtm_donne, mtm_net=mtm_recu - mtm_donne, financement=fin,
                pnl_marche=(mtm_recu - mtm_donne) + fin, pnl_prix_aller=(carry_recu - carry_donne) + fin,
                sensi_nominale_mes=som(mes, "sensi_nominale"), sensi_nominale_cp=som(cp, "sensi_nominale"))
