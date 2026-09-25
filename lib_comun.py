# =====================================================================================
# Utilidades compartidas entre el generador de datos y el ETL.
# Vive en un solo lugar para no duplicar la logica de normalizacion entre los dos scripts
# (si cambia la regla de como se limpia un nombre de empresa, cambia en un solo sitio).
# =====================================================================================

import unicodedata


def normaliza(txt: str) -> str:
    """Mayusculas, sin tildes, sin sufijos legales, espacios colapsados.
    Es la clave que se usa para cruzar el mismo nombre de empresa escrito distinto
    entre CRM, Billing y Contratos."""
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode("ascii")
    t = t.upper().strip()
    for suf in [" S.A.S.", " SAS", " S.A.", " SA", " LTDA", " LTDA.", " E.U.", " EU"]:
        if t.endswith(suf.upper()):
            t = t[: -len(suf)].strip()
    t = " ".join(t.split())
    return t
