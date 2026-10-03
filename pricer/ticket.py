"""Ticket d operation en PDF, une page, charte Point Adju."""
from __future__ import annotations
import io, datetime as dt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

BLEU = colors.HexColor("#0071CE"); ROUGE = colors.HexColor("#C9285A"); GRIS = colors.HexColor("#5E6675"); INK = colors.HexColor("#1B2333"); CLAIR = colors.HexColor("#F0F7FC")


def ticket_pdf(op: dict, titre, auteur: str, fmt_pct, fmt_mnt, logo_png: bytes | None = None) -> bytes:
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); W, H = A4
    c.setFillColor(BLEU); c.rect(0, H - 34 * mm, W, 34 * mm, fill=1, stroke=0)
    c.setFillColor(ROUGE); c.rect(0, H - 35.5 * mm, W, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica", 8); c.drawString(15 * mm, H - 12 * mm, "CREDIT DU MAROC  ·  SALLE DES MARCHES")
    c.setFont("Helvetica-Bold", 20); c.drawString(15 * mm, H - 24 * mm, "TICKET D'OPERATION")
    c.setFont("Helvetica", 10); c.drawRightString(W - 15 * mm, H - 14 * mm, f"N° {op.get('id', '')}  ·  {dt.date.fromisoformat(op['date']):%d/%m/%Y}")
    c.setFont("Helvetica", 8); c.drawRightString(W - 15 * mm, H - 22 * mm, f"saisi par {auteur or ''} le {op.get('saisie_le', '')}")
    sens = op["sens"].upper(); c.setFillColor(ROUGE if op["sens"] == "Vente" else BLEU)
    c.setFont("Helvetica-Bold", 28); c.drawString(15 * mm, H - 52 * mm, sens)
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 13); c.drawString(15 * mm, H - 62 * mm, titre.libelle if titre else op["code"])
    c.setFillColor(GRIS); c.setFont("Helvetica", 9); c.drawString(15 * mm, H - 68 * mm, f"Code {op['code']}" + (f"  ·  ISIN {titre.isin}" if titre and titre.isin else "") + (f"  ·  echeance {titre.echeance:%d/%m/%Y}  ·  coupon {fmt_pct(titre.taux_facial, 2)}" if titre else ""))
    nominal = float(op["nominal"]); px = float(op["prix_plein"]); r = float(op["taux"]); montant = nominal * px / 100
    y = H - 84 * mm
    lignes = [("Contrepartie", op.get("contrepartie", "") or "-"), ("Nominal", fmt_mnt(nominal) + " MAD"), ("Prix plein", f"{px:.4f} %".replace(".", ",")), ("Taux", fmt_pct(r)),
              ("Montant a regler", fmt_mnt(montant, 2) + " MAD"), ("Date d'operation", f"{dt.date.fromisoformat(op['date']):%d/%m/%Y}"), ("Commentaire", op.get("commentaire", "") or "-")]
    for i, (k, v) in enumerate(lignes):
        if i % 2 == 0:
            c.setFillColor(CLAIR); c.rect(15 * mm, y - 4 * mm, W - 30 * mm, 10 * mm, fill=1, stroke=0)
        c.setFillColor(GRIS); c.setFont("Helvetica", 9); c.drawString(18 * mm, y, k)
        c.setFillColor(INK); c.setFont("Helvetica-Bold" if k in ("Montant a regler", "Nominal") else "Helvetica", 11); c.drawRightString(W - 18 * mm, y, v)
        y -= 10 * mm
    c.setFillColor(BLEU); c.rect(0, 0, W, 12 * mm, fill=1, stroke=0); c.setFillColor(ROUGE); c.rect(0, 12 * mm, W, 1 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica", 8); c.drawString(15 * mm, 5 * mm, "Document interne  ·  genere par le pricer  ·  " + dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
    c.showPage(); c.save()
    return buf.getvalue()
