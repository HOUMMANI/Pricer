# Pricer Valorisation Maroc – version 2 (Streamlit)

Six pages, chacune fait une chose. Tout s'enregistre dans `data/` (fichiers CSV datés, relus par les autres pages).

## Installation
```
pip install -r requirements.txt
streamlit run app.py
```

## Barre latérale
Date de valorisation · lecture de la courbe (taux de la ligne, ou interpolation sur les tenors) · courbe utilisée (courbe publiée de la date, ou courbe du jour = BKAM + cotations eBond).

## Pages
1. **Courbe** : lecture BKAM (site, ou fichier CSV/HTML exporté du site), saisie des neuf tenors, historisation automatique ; cotations eBond du jour (collées depuis Bloomberg, en taux) ; tableau des tenors avec équivalents actuariels, graphe, lignes publiées, comparaison entre deux dates.
2. **Cotation** : un titre, une date, une courbe ; méthodes tenors et lignes côte à côte ; cotation par le taux ou par le prix à la main ; détail complet (régime de la circulaire, dates de coupon, prix plein, pied, couru, sensi, duration, PVBP, convexité) ; projection du titre à d'autres dates.
3. **Portefeuille** : positions à la date = dernière photo + opérations enregistrées depuis ; photo chargée depuis Excel (canevas téléchargeable) ; valorisation ligne à ligne et globale ; onglets tranches et limites ; export Excel.
4. **Opérations** : saisie à la main (prix plein ou taux, l'autre se déduit, écart d'exécution contre la courbe) ou import par canevas Excel ; journal historisé ; suppression.
5. **P&L** : entre deux dates, période par période sur les courbes de l'historique : carry, effet courbe, trading, financement, total ; cumul ; export.
6. **Swap** : mes lignes contre celles de la contrepartie, volume, mode sensi égale ou volume égal, dates aller et retour ; jambes aux deux dates, soulte, carry net, MtM net, P&L selon retour aux prix d'aller ou au marché ; effet sur la sensi.

Référentiel (832 titres Maroclear, remplaçable) et Paramètres (taux de financement, méthode par défaut, règle eBond, grille des limites).

## Conventions
- Formules de la circulaire 02/04, identiques au classeur (voir version 1 pour la vérification sur 41 lignes).
- Positions : quantités en nombre de titres ; opérations en nominal (MAD) ; prix en % ; taux en %.
- P&L d'une période = variation de valeur de marché + cash des opérations + coupons et remboursements encaissés − financement ; carry = variation du couru + flux encaissés ; effet courbe = réévaluation des positions d'ouverture hors carry ; trading = valeur des opérations contre leur cash ; financement = valeur d'ouverture × taux × jours / 360.
- Courbe du jour : trois règles (BKAM seule ; lignes eBond remplaçant les lignes cotées puis tenors recalculés ; décalage des tenors de la variation moyenne). À affiner ensemble.

## Fichiers de données
`courbes.csv` (historique, une ligne par date), `lignes.csv` (lignes publiées), `ebond.csv`, `positions.csv` (photos), `operations.csv` (journal), `referentiel.csv`, `parametres.json`, `positions_exemple.csv` (portefeuille du classeur, photo du 08/09/2026 déjà enregistrée).

## Identification
À l'ouverture, identifiant et mot de passe. Compte de départ : `admin` / `admin`, à changer dans PARAMÈTRES. Tous les utilisateurs ont l'utilisation complète ; chacun peut ajouter un utilisateur dans PARAMÈTRES. Les mots de passe sont hachés dans `data/utilisateurs.csv`. Le CARNET signe chaque ordre du nom de l'utilisateur.

## Six fonctions de plus
1. **Radar des clients** (CARNET › Radar) : profil de chaque client depuis les ordres ; « je cherche des acheteurs de 5 ans » donne qui appeler, dans l'ordre.
2. **Courbe des ordres** (COURBE) : courbe implicite des ordres valables, comparée à BAM et eBond.
3. **Mémoire des négociations** (COTER, champ Client) : derniers prix donnés et demandés sur la ligne et ses voisines.
4. **Ticket PDF** (OPÉRER) : une page par opération, charte Point Adju.
5. **Résumé de 17 h** (RÉSUMÉ) : courbe, opérations, P&L, ordres valables, matchs ; mail prêt ; envoi automatique par `python resume_17h.py` planifié (SMTP dans PARAMÈTRES).
6. **Alertes** : badge dans le rail et liste en haut : limites, ordres qui expirent, matchs croisables, eBond qui croise un ordre client.

## SIMULATEUR
Trois zones. Contexte : le portefeuille du jour, sa sensibilité par tenor. Travail : opérations « et si » (sens, code, nominal), courbe à la main (neuf curseurs, préréglages), horizon et financement. Résultat : avant / après sur tous les agrégats ; effet courbe immédiat et cash des opérations ; onglets Limites (avant / après), Horizon (carry, temps, courbe, financement, total), Scénarios (quatorze déformations en réévaluation complète, pire scénario), VaR (historique des variations de courbe appliquées au portefeuille, 95 % et 99 %), Par ligne (gagnants et perdants), Tenors (sensibilité par tenor avant / après), Couverture (nominal d'une ligne qui annule la sensibilité d'un tenor). Export Excel.

## Dates, tiers, ventilation, intermédiation
- Chaque opération porte une **date d'opération** et une **date valeur**. Les positions et le P&L se lisent dans l'une ou l'autre base (barre latérale « Positions en », et choix dans P&L).
- **Tiers** (CONTACTS) : SDG, Fonds (avec sa SDG et son dépositaire), Banque, Assurance, CDG, Dépositaire, Autre ; e-mails rattachés à chaque tiers.
- **Contrepartie** et **Pour le compte de** : quand on passe par une banque pour un OPCVM, la banque est la contrepartie, l'OPCVM le client final ; ses contacts sont en copie.
- **Ventilation** : une opération en bloc avec une SDG se ventile sur ses fonds ; chaque ligne de ventilation génère son mail, dépositaire en copie ; la position reste portée par le bloc.
- **Intermédiation** : deux jambes, achat au vendeur puis vente à l'acheteur, dates libres ; marge, financement du portage et résultat ; les deux jambes sont liées dans le journal.
