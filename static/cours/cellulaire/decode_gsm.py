#!/usr/bin/env python3
"""Décodeur minimal d'une trace GSM Um au format XML (<l1 ...><l2 .../></l1>).

Usage : python3 -I decode_gsm.py sms.xml

Couvre ce qui sert pour le TP : en-têtes RR du BCCH/CCCH, LAPDm des canaux
dédiés (SDCCH, SACCH), messages L3 RR/MM, et SMS (CP / RP / TPDU) avec
réassemblage des segments LAPDm (bit M). Ce n'est pas un décodeur complet.

Correspondance des numéros de canal déduite du contenu de la trace
(convention propre à l'outil de capture, pas celle de GSMTAP) :
  80 = BCCH, 96 = CCCH (PCH/AGCH), 112 = SACCH, 128 = SDCCH
"""
import sys
import xml.etree.ElementTree as ET

CHANNELS = {"80": "BCCH", "96": "CCCH", "112": "SACCH", "128": "SDCCH"}

RR = {0x3F: "Immediate Assignment", 0x21: "Paging Request Type 1",
      0x22: "Paging Request Type 2", 0x24: "Paging Request Type 3",
      0x19: "System Information 1", 0x1A: "System Information 2",
      0x1B: "System Information 3", 0x1C: "System Information 4",
      0x1D: "System Information 5", 0x1E: "System Information 6",
      0x35: "Ciphering Mode Command", 0x27: "Paging Response",
      0x0D: "Channel Release"}
MM = {0x24: "CM Service Request", 0x1A: "TMSI Reallocation Command",
      0x08: "Location Updating Request", 0x12: "Authentication Request",
      0x18: "Identity Request", 0x21: "CM Service Accept"}
CP = {0x01: "CP-DATA", 0x04: "CP-ACK", 0x10: "CP-ERROR"}
RP = {0x00: "RP-DATA (MS->réseau)", 0x01: "RP-DATA (réseau->MS)",
      0x02: "RP-ACK (MS->réseau)", 0x03: "RP-ACK (réseau->MS)"}


def bcd(b):
    """Semi-octets BCD inversés (chiffre de poids faible d'abord), F = bourrage."""
    out = ""
    for x in b:
        for n in (x & 0x0F, x >> 4):
            if n != 0xF:
                out += str(n)
    return out


def mobile_id(b):
    """Mobile Identity (TS 24.008, 10.5.1.4) : IMSI, IMEI ou TMSI."""
    kind = b[0] & 0x07
    if kind == 4:
        return "TMSI " + b[1:5].hex().upper()
    if kind == 0:
        return "aucune identité"
    digits = str(b[0] >> 4) + bcd(b[1:])
    return {1: "IMSI ", 2: "IMEI ", 3: "IMEISV "}.get(kind, "ID ") + digits


def gsm7(data, nchars):
    """Décompresse nchars septets de l'alphabet GSM 7 bits (cas ASCII seulement)."""
    bits = int.from_bytes(data, "little")
    return "".join(chr((bits >> (7 * i)) & 0x7F) for i in range(nchars))


def address(b):
    """Adresse (longueur, TON/NPI, chiffres BCD). Renvoie (texte, taille consommée)."""
    return ("+" if b[1] & 0x70 == 0x10 else "") + bcd(b[2:2 + b[0] - 1]), 1 + b[0]


def lai(b):
    """Location Area Identity : MCC, MNC (BCD) et LAC."""
    mcc = "%d%d%d" % (b[0] & 15, b[0] >> 4, b[1] & 15)
    mnc = "%d%d" % (b[2] & 15, b[2] >> 4) + ("" if b[1] >> 4 == 15 else str(b[1] >> 4))
    return "MCC %s MNC %s LAC 0x%s" % (mcc, mnc, b[3:5].hex().upper())


def tpdu(t):
    """TPDU SMS-DELIVER (seul cas présent dans la trace, sens descendant)."""
    if t[0] & 0x03 != 0:
        return "TPDU type %d non décodé" % (t[0] & 3)
    ndig = t[1]
    oa = ("+" if t[2] & 0x70 == 0x10 else "") + bcd(t[3:3 + (ndig + 1) // 2])
    i = 3 + (ndig + 1) // 2
    pid, dcs = t[i], t[i + 1]
    ts = bcd(t[i + 2:i + 9])          # AAMMJJhhmmss + fuseau
    udl = t[i + 9]
    text = gsm7(t[i + 10:], udl) if dcs == 0 else t[i + 10:].hex()
    date = "20%s-%s-%s %s:%s:%s" % (ts[0:2], ts[2:4], ts[4:6], ts[6:8], ts[8:10], ts[10:12])
    return "SMS-DELIVER de %s, PID=%d DCS=%d, horodatage %s, texte %r" % (oa, pid, dcs, date, text)


def l3(m):
    """Décode un message de couche 3 (en-tête PD/TI + type)."""
    if not m:
        return "(vide)"
    pd, ti = m[0] & 0x0F, m[0] >> 4
    if pd == 6:                      # RR
        name = RR.get(m[1], "RR 0x%02X" % m[1])
        if m[1] == 0x21:             # Paging Request Type 1
            ids = [mobile_id(m[4:4 + m[3]])]
            i = 4 + m[3]
            if i + 1 < len(m) and m[i] == 0x17:          # 2e identité optionnelle
                ids.append(mobile_id(m[i + 2:i + 2 + m[i + 1]]))
            name += " : " + ", ".join(ids)
        elif m[1] == 0x3F:
            # m[2] = modes, m[3:6] = Channel Description, m[6:9] = Request Reference
            ch = m[3]
            if m[2] & 0x10:          # bit TD : assignation d'un TBF GPRS
                return name + " : TBF GPRS (canal paquet), RA=0x%02X" % m[6]
            if ch >> 6 == 1:
                sub = "SDCCH/8 sous-canal %d" % ((ch >> 3) & 7)
            elif ch >> 3 == 1:
                sub = "TCH/F"
            else:
                sub = "chan_nr 0x%02X" % ch
            hop = "saut de fréquence" if m[4] & 0x10 else "ARFCN %d" % (((m[4] & 3) << 8) | m[5])
            name += " : %s, TS%d, %s, RA=0x%02X, TA=%d" % (sub, ch & 7, hop, m[6], m[9])
        elif m[1] == 0x27:
            name += " : " + mobile_id(m[8:8 + m[7]])
        elif m[1] == 0x35:
            sc, alg = m[2] & 1, (m[2] >> 1) & 7
            name += " : chiffrement %s, A5/%d" % ("activé" if sc else "inactif", alg + 1)
        elif m[1] in (0x1B, 0x1E):   # SI3, SI6 : Cell Identity puis LAI
            name += " : CI=0x%s, %s" % (m[2:4].hex().upper(), lai(m[4:9]))
        elif m[1] == 0x1C:           # SI4 : LAI en tête
            name += " : " + lai(m[2:7])
        return name
    if pd == 5:                      # MM
        name = MM.get(m[1] & 0x3F, "MM 0x%02X" % m[1])
        if m[1] & 0x3F == 0x24:
            name += " : service %d (4 = SMS), %s" % (m[2] & 0x0F, mobile_id(m[8:8 + m[7]]))
        elif m[1] & 0x3F == 0x1A:
            name += " : nouveau " + mobile_id(m[8:8 + m[7]])
        return name
    if pd == 9:                      # SMS, couche CP (TS 24.011)
        name = "%s (TI %d)" % (CP.get(m[1], "CP 0x%02X" % m[1]), ti & 7)
        if m[1] == 0x01:
            rp = m[3:3 + m[2]]
            name += " / %s ref %d" % (RP.get(rp[0], "RP 0x%02X" % rp[0]), rp[1])
            if rp[0] == 0x01:
                orig, n = address(rp[2:])
                j = 2 + n
                j += 1 + rp[j]       # RP-Destination (vide en descendant)
                name += ", SMSC %s / %s" % (orig, tpdu(rp[j + 1:j + 1 + rp[j]]))
        return name
    return "PD %d non décodé" % pd


def lapdm(b):
    """En-tête LAPDm (address, control, length). Renvoie (texte, payload, bit M)."""
    a, c, l = b[0], b[1], b[2]
    sapi = (a >> 2) & 7
    n, more = l >> 2, (l >> 1) & 1
    if c & 1 == 0:
        kind = "I N(S)=%d N(R)=%d" % ((c >> 1) & 7, c >> 5)
    elif c & 3 == 1:
        kind = {0: "RR", 1: "RNR", 2: "REJ"}.get((c >> 2) & 3, "S?") + " N(R)=%d" % (c >> 5)
    else:
        kind = {0x03: "UI", 0x2F: "SABM", 0x63: "UA", 0x43: "DISC", 0x0F: "DM"}.get(c & 0xEF, "U?")
    return "SAPI %d %-15s" % (sapi, kind), b[3:3 + n], more


def main(path):
    root = ET.parse(path).getroot()
    buf = {}                         # segments LAPDm en attente
    for e in root.iter("l1"):
        ch = CHANNELS.get(e.get("logicalchannel"), e.get("logicalchannel"))
        fn = int(e.get("sequence"))
        raw = bytes.fromhex(e.get("data"))
        head = "%s FN=%d %-5s" % (e.get("direction")[0].upper(), fn, ch)
        if ch in ("BCCH", "CCCH"):
            n = raw[0] >> 2          # L2 pseudo-length
            msg = raw[1:1 + n]
            if ch == "BCCH":
                head += " TC=%d" % ((fn // 51) % 8)
            print(head, l3(msg) if n else "(pseudo-length nulle : rien à décoder)")
        else:
            if raw[2] == 0x2B:       # champ longueur = octet de bourrage : bloc vide
                print(head, "(bloc de bourrage 0x2B)")
                continue
            info, payload, more = lapdm(raw)
            key = (ch, (raw[0] >> 2) & 7)          # réassemblage par canal et SAPI
            if more:
                buf[key] = buf.get(key, b"") + payload
                print(head, info, "segment (M=1), %d octets" % len(payload))
                continue
            payload = buf.pop(key, b"") + payload
            print(head, info, l3(payload) if payload else "(sans contenu L3)")


if __name__ == "__main__":
    main(sys.argv[1])
