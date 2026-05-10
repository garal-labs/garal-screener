"""
Servicio de cálculos financieros.
Toda la lógica de FIFO, plusvalías y rentabilidades vive aquí.
"""
from typing import List, Dict, Any
from collections import deque


class VentaInvalidaError(ValueError):
    """Se lanza cuando se intenta vender más de lo disponible en los lotes FIFO."""


def calcular_posicion_fifo(movimientos: List[Any]) -> Dict:
    """
    Dado una lista de movimientos ordenados por fecha ASC,
    calcula la posición actual usando el método FIFO.

    Devuelve:
        cantidad_actual     → acciones/participaciones que tienes ahora
        coste_total         → lo que te costaron en EUR (con comisiones)
        precio_medio        → coste_total / cantidad_actual
        plusvalia_realizada → ganancia/pérdida de las ventas ya cerradas
        lotes               → lotes FIFO pendientes (para debug o detalle)
    """
    # Cola FIFO: cada elemento es [cantidad_restante, precio_eur, fecha]
    lotes = deque()
    plusvalia_realizada = 0.0

    # Orden determinístico: fecha ASC, id ASC para desempate intradía
    for mov in sorted(movimientos, key=lambda m: (m.fecha, m.id)):
        precio_eur = _precio_en_eur(mov)
        comision = mov.comision or 0.0

        if mov.tipo == "compra":
            # Añadimos lote: precio unitario incluyendo comisión prorrateada
            precio_unitario = precio_eur + (comision / mov.cantidad)
            lotes.append([mov.cantidad, precio_unitario, mov.fecha])

        elif mov.tipo == "venta":
            cantidad_vender = mov.cantidad
            coste_vendido = 0.0

            while cantidad_vender > 0 and lotes:
                lote = lotes[0]
                cantidad_lote, precio_lote, _ = lote

                if cantidad_lote <= cantidad_vender:
                    # Consumimos el lote entero
                    coste_vendido += cantidad_lote * precio_lote
                    cantidad_vender -= cantidad_lote
                    lotes.popleft()
                else:
                    # Consumimos parte del lote
                    coste_vendido += cantidad_vender * precio_lote
                    lote[0] -= cantidad_vender
                    cantidad_vender = 0

            # Si después del while todavía queda por vender, los datos son inconsistentes
            if cantidad_vender > 0:
                raise VentaInvalidaError(
                    f"Movimiento id={mov.id}: intento de vender {mov.cantidad} unidades "
                    f"pero los lotes FIFO no tienen suficiente stock."
                )

            # Ingreso de la venta en EUR menos comisión
            ingreso_venta = (mov.precio * mov.cantidad * _tipo_cambio(mov)) - comision
            plusvalia_realizada += ingreso_venta - coste_vendido

    # Calculamos posición actual desde lotes restantes
    cantidad_actual = sum(l[0] for l in lotes)
    coste_total = sum(l[0] * l[1] for l in lotes)
    precio_medio = coste_total / cantidad_actual if cantidad_actual > 0 else 0.0

    return {
        "cantidad_actual": round(cantidad_actual, 6),
        "coste_total": round(coste_total, 2),
        "precio_medio": round(precio_medio, 4),
        "plusvalia_realizada": round(plusvalia_realizada, 2),
        "lotes_pendientes": [
            {"cantidad": round(l[0], 6), "precio_coste": round(l[1], 4), "fecha": str(l[2])}
            for l in lotes
        ]
    }


def calcular_plusvalia_latente(posicion: Dict, precio_actual_eur: float) -> Dict:
    """
    Con la posición FIFO calculada y el precio actual de mercado,
    calcula la plusvalía latente (no realizada).
    """
    cantidad = posicion["cantidad_actual"]
    coste = posicion["coste_total"]
    valor_actual = round(precio_actual_eur * cantidad, 2)
    plusvalia_latente = round(valor_actual - coste, 2)
    rentabilidad_pct = round((plusvalia_latente / coste * 100), 2) if coste > 0 else 0.0

    return {
        "valor_actual": valor_actual,
        "plusvalia_latente": plusvalia_latente,
        "rentabilidad_pct": rentabilidad_pct,
        "plusvalia_total": round(plusvalia_latente + posicion["plusvalia_realizada"], 2),
    }


def calcular_resumen_cartera(posiciones: List[Dict]) -> Dict:
    """
    Agrega todas las posiciones en métricas globales de cartera.
    Cada posición debe tener: valor_actual, coste_total, plusvalia_latente,
    plusvalia_realizada, rentabilidad_pct.
    """
    valor_total = sum(p.get("valor_actual") or 0 for p in posiciones)
    coste_total = sum(p.get("coste_total", 0) for p in posiciones)
    plusvalia_latente = sum(p.get("plusvalia_latente") or 0 for p in posiciones)
    plusvalia_realizada = sum(p.get("plusvalia_realizada", 0) for p in posiciones)
    plusvalia_total = plusvalia_latente + plusvalia_realizada
    # Rentabilidad sobre coste total (latente + realizada)
    rentabilidad_total_pct = round((plusvalia_total / coste_total * 100), 2) if coste_total > 0 else 0.0

    return {
        "valor_total": round(valor_total, 2),
        "coste_total": round(coste_total, 2),
        "plusvalia_latente": round(plusvalia_latente, 2),
        "plusvalia_realizada": round(plusvalia_realizada, 2),
        "plusvalia_total": round(plusvalia_total, 2),
        "rentabilidad_pct": rentabilidad_total_pct,
        "num_posiciones": len([p for p in posiciones if p.get("cantidad_actual", 0) > 0]),
    }


def agrupar_por_campo(posiciones: List[Dict], campo: str) -> List[Dict]:
    """
    Agrupa posiciones por sector, país, tipo, etc.
    Usa valor_actual si hay precio; si no, usa coste_total como fallback.
    Devuelve lista ordenada de mayor a menor peso.
    """
    grupos: Dict[str, float] = {}

    for pos in posiciones:
        clave = pos.get(campo) or "Sin clasificar"
        # valor_actual puede ser None si FMP no devolvio precio para ese ticker
        valor = pos.get("valor_actual") or pos.get("coste_total") or 0
        grupos[clave] = grupos.get(clave, 0) + valor

    valor_total = sum(grupos.values())

    resultado = [
        {
            "nombre": k,
            "valor": round(v, 2),
            "peso_pct": round((v / valor_total * 100), 2) if valor_total > 0 else 0,
        }
        for k, v in grupos.items()
    ]
    return sorted(resultado, key=lambda x: x["valor"], reverse=True)


# ── Helpers privados ──────────────────────────────────────────────────────────

def _tipo_cambio(mov) -> float:
    """
    Devuelve el tipo de cambio a aplicar.
    Si no se ha introducido, asume 1.0 (misma moneda que EUR o ya en EUR).
    """
    # is not None para no confundir tipo_cambio=0.0 (inválido) con ausente
    return mov.tipo_cambio if mov.tipo_cambio is not None else 1.0


def _precio_en_eur(mov) -> float:
    """
    Convierte el precio del movimiento a EUR aplicando tipo de cambio.
    """
    return mov.precio * _tipo_cambio(mov)