"""
Pruebas del motor de puntaje (src/radar.py). Solo usan la libreria estandar.

    .venv/bin/python -m unittest discover -s tests -v

Casi todas usan una configuracion pequena y propia (no config/filtros.yaml), para que ajustar los pesos
reales del negocio no rompa las pruebas. Las del final (RealConfig) solo vigilan que la configuracion
real y los datos de ejemplo sigan funcionando de punta a punta.
"""

import copy
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import radar  # noqa: E402

PASADO, FUTURO = "2000-01-01T00:00:00.000", "2999-01-01T00:00:00.000"

PERFIL = {
    "territorio_prioritario": ["Santander"],
    "capacidad": {"cuantia_minima_cop": 5_000_000, "cuantia_maxima_sola_cop": 2_000_000_000,
                  "cuantia_maxima_union_temporal_cop": 8_000_000_000},
    "modalidad_participacion": {"obra_con_instalacion": False},
}

FILTROS = {
    "incluir": {
        "nucleo": {"peso": 40, "terminos": ["variador de velocidad", "plc"]},
        "catalogo": {"peso": 30, "terminos": ["material electrico", "cable electrico"]},
    },
    "excluir": ["interventoria", "papeleria"],
    "excluir_estado": ["Cancelado", "Adjudicado"],
    "excluir_modalidad": ["Contratación directa"],
    "marcar_union_temporal": {"tipos_contrato": ["Obra"], "terminos": ["montaje"]},
    "puntaje": {"bono_territorio_prioritario": 15, "bono_entidad_conocida": 10,
                "penalizacion_fuera_de_cuantia": -40, "umbral_alerta": 30,
                "penalizacion_requiere_aliado": -15, "umbral_revisar": 5},
    "niveles": {"alta": 50, "media": 30},
    "entidades_conocidas": ["ESSA"],
    "ajustes_contrato": {
        "favorables": {"bono": 15, "tipos": ["Suministros", "Compraventa"]},
        "desfavorables": {"penalizacion": -15, "tipos": ["Prestación de servicios"],
                          "salvo_si_menciona": ["suministro de"]},
        "mantenimiento": {"penalizacion": -20, "tope_puntaje": 29, "terminos": ["mantenimiento"],
                          "salvo_si_menciona": ["suministro de", "adquisicion de"]},
    },
    "ajustes_modalidad": {
        "favorables": {"bono": 10, "modalidades": ["Mínima cuantía"]},
        "solo_informacion": {"penalizacion": -10, "modalidades": ["Solicitud de información a los Proveedores"]},
    },
}


def proceso(texto="variador de velocidad", **extra):
    """Un proceso minimo y valido; cada prueba cambia solo lo que le interesa."""
    base = {"descripci_n_del_procedimiento": texto, "nombre_del_procedimiento": "",
            "estado_de_apertura_del_proceso": "Abierto", "precio_base": "50000000"}
    base.update(extra)
    return base


def evaluar(p, umbral=None, **cambios_filtros):
    f = copy.deepcopy(FILTROS)
    f.update(cambios_filtros)
    return radar.evaluar(p, PERFIL, f, umbral)


class Texto(unittest.TestCase):
    def test_normalizar_quita_tildes_mayusculas_y_espacios(self):
        self.assertEqual(radar.normalizar("  Ñandú   ELÉCTRICO \n"), "nandu electrico")

    def test_normalizar_vacios(self):
        self.assertEqual(radar.normalizar(None), "")
        self.assertEqual(radar.normalizar(""), "")

    def test_limpiar_quita_caracteres_de_control(self):
        self.assertEqual(radar.limpiar("a\x1b[31mb\x00c"), "a [31mb c")
        self.assertEqual(radar.limpiar(None), "")

    def test_a_numero(self):
        self.assertEqual(radar.a_numero("1500.5"), 1500.5)
        self.assertEqual(radar.a_numero(None), 0.0)
        self.assertEqual(radar.a_numero("sin dato"), 0.0)

    def test_url_segura_solo_https(self):
        self.assertEqual(radar.url_segura("https://community.secop.gov.co/x"), "https://community.secop.gov.co/x")
        self.assertEqual(radar.url_segura({"url": "https://a.co/b"}), "https://a.co/b")
        self.assertEqual(radar.url_segura("http://a.co"), "")
        self.assertEqual(radar.url_segura("javascript:alert(1)"), "")
        self.assertEqual(radar.url_segura(None), "")


class Contiene(unittest.TestCase):
    """Busqueda por palabra completa, con singular y plural."""

    def test_acepta_plural_del_termino(self):
        self.assertTrue(radar.contiene("compra de obras menores", "obra"))
        self.assertTrue(radar.contiene("suministro de cables", "cable"))

    def test_acepta_singular_si_el_termino_esta_en_plural(self):
        self.assertTrue(radar.contiene("un variador de velocidad", "variadores de velocidad"))

    def test_cada_palabra_del_termino_admite_su_plural(self):
        self.assertTrue(radar.contiene("variadores de velocidades", "variador de velocidad"))

    def test_no_coincide_dentro_de_otra_palabra(self):
        self.assertFalse(radar.contiene("compra de grupos electrogenos", "ups"))
        self.assertFalse(radar.contiene("no se puede obrar asi", "obra"))

    def test_si_coincide_la_sigla_sola(self):
        self.assertTrue(radar.contiene("instalacion de ups y estabilizadores", "ups"))

    def test_espacios_flexibles(self):
        self.assertTrue(radar.contiene("variador   de    velocidad", "variador de velocidad"))

    def test_limite_con_signos_de_puntuacion(self):
        self.assertTrue(radar.contiene("suministro: cable, canaleta.", "canaleta"))

    def test_palabras_cortas_no_se_pluralizan(self):
        # «de» no debe volverse «des»/«dees» y coincidir con otra cosa
        self.assertFalse(radar.contiene("compra des cable", "compra de cable"))

    def test_el_termino_se_normaliza(self):
        self.assertTrue(radar.contiene("alumbrado publico", "Alumbrado Público"))


class Descarte(unittest.TestCase):
    def test_sin_texto_no_aplica(self):
        self.assertIsNone(evaluar(proceso("")))

    def test_proceso_cerrado_no_aplica(self):
        self.assertIsNone(evaluar(proceso(estado_de_apertura_del_proceso="Cerrado")))

    def test_apertura_vacia_no_se_descarta(self):
        self.assertIsNotNone(evaluar(proceso(estado_de_apertura_del_proceso="")))

    def test_estado_del_procedimiento_excluido(self):
        self.assertIsNone(evaluar(proceso(estado_del_procedimiento="Cancelado")))
        self.assertIsNotNone(evaluar(proceso(estado_del_procedimiento="Publicado")))

    def test_fecha_de_cierre_pasada_descarta_pero_vacia_o_futura_no(self):
        self.assertIsNone(evaluar(proceso(fecha_de_recepcion_de=PASADO)))
        self.assertIsNotNone(evaluar(proceso(fecha_de_recepcion_de=FUTURO)))
        self.assertIsNotNone(evaluar(proceso(fecha_de_recepcion_de="")))

    def test_sin_coincidencias_no_aplica(self):
        self.assertIsNone(evaluar(proceso("compra de sillas de oficina")))

    def test_la_exclusion_gana_aunque_haya_coincidencia(self):
        self.assertIsNone(evaluar(proceso("interventoria de variador de velocidad")))

    def test_modalidad_excluida(self):
        self.assertIsNone(evaluar(proceso(modalidad_de_contratacion="Contratación directa")))


class Puntaje(unittest.TestCase):
    def test_un_grupo_aporta_su_peso_una_sola_vez(self):
        # dos terminos del mismo grupo («nucleo», 40) no suman 80
        r = evaluar(proceso("variador de velocidad con plc"))
        self.assertEqual(r["puntaje"], 40)
        self.assertEqual(r["coincidencias"], ["plc", "variador de velocidad"])

    def test_grupos_distintos_se_suman(self):
        self.assertEqual(evaluar(proceso("variador de velocidad y cable electrico"))["puntaje"], 70)

    def test_texto_repetido_no_infla(self):
        self.assertEqual(evaluar(proceso("plc plc plc plc"))["puntaje"], 40)

    def test_bono_de_territorio(self):
        self.assertEqual(evaluar(proceso(departamento_entidad="Santander"))["puntaje"], 55)
        self.assertEqual(evaluar(proceso(departamento_entidad="Chocó"))["puntaje"], 40)

    def test_bono_de_entidad_conocida(self):
        r = evaluar(proceso(entidad="ESSA S.A. E.S.P."))
        self.assertEqual(r["puntaje"], 50)
        self.assertIn("entidad que ya compra este material", r["notas"])

    def test_valor_en_cero_no_penaliza_y_se_marca(self):
        r = evaluar(proceso(precio_base="0"))
        self.assertEqual(r["puntaje"], 40)
        self.assertIn("sin valor publicado, revisar manualmente", r["notas"])

    def test_valor_por_debajo_del_minimo_penaliza(self):
        self.assertEqual(evaluar(proceso(precio_base="1000000"), umbral=0)["puntaje"], 0)  # 40 - 40

    def test_valor_muy_por_encima_penaliza(self):
        r = evaluar(proceso(precio_base="9000000000"), umbral=0)
        self.assertEqual(r["puntaje"], 0)
        self.assertIn("cuantia muy por encima de la capacidad", r["notas"])

    def test_valor_alto_solo_avisa_union_temporal(self):
        r = evaluar(proceso(precio_base="3000000000"))
        self.assertEqual(r["puntaje"], 40)
        self.assertIn("cuantia alta, evaluar union temporal", r["notas"])

    def test_el_puntaje_nunca_pasa_de_100_ni_baja_de_0(self):
        alto = evaluar(proceso("variador de velocidad y cable electrico", departamento_entidad="Santander",
                               entidad="ESSA", tipo_de_contrato="Suministros",
                               modalidad_de_contratacion="Mínima cuantía"))
        self.assertEqual(alto["puntaje"], 100)
        bajo = evaluar(proceso(precio_base="1"), umbral=0)
        self.assertEqual(bajo["puntaje"], 0)

    def test_bajo_el_umbral_no_se_alerta(self):
        self.assertIsNone(evaluar(proceso("plc", tipo_de_contrato="Prestación de servicios",
                                          precio_base="1000000")))

    def test_umbral_explicito_deja_ver_los_de_revisar(self):
        p = proceso("plc", tipo_de_contrato="Prestación de servicios")  # 40 - 15 = 25
        self.assertIsNone(evaluar(p))
        self.assertEqual(evaluar(p, umbral=5)["nivel"], "revisar")

    def test_niveles(self):
        self.assertEqual(evaluar(proceso("variador de velocidad y cable electrico"))["nivel"], "alta")
        self.assertEqual(evaluar(proceso("plc"))["nivel"], "media")


class TipoYModalidad(unittest.TestCase):
    def test_tipo_favorable_suma(self):
        self.assertEqual(evaluar(proceso(tipo_de_contrato="Suministros"))["puntaje"], 55)

    def test_tipo_desfavorable_resta(self):
        self.assertEqual(evaluar(proceso(tipo_de_contrato="Prestación de servicios"), umbral=0)["puntaje"], 25)

    def test_tipo_desfavorable_no_resta_si_el_objeto_compra_bienes(self):
        r = evaluar(proceso("suministro de variador de velocidad", tipo_de_contrato="Prestación de servicios"))
        self.assertEqual(r["puntaje"], 40)

    def test_modalidad_favorable_suma(self):
        self.assertEqual(evaluar(proceso(modalidad_de_contratacion="Mínima cuantía"))["puntaje"], 50)

    def test_solo_informacion_resta_y_avisa(self):
        r = evaluar(proceso(modalidad_de_contratacion="Solicitud de información a los Proveedores"))
        self.assertEqual(r["puntaje"], 30)
        self.assertIn("solo solicitud de informacion, no es oferta", r["notas"])


class Mantenimiento(unittest.TestCase):
    def test_mantenimiento_resta_y_tiene_tope(self):
        # 40 + 30 + 15 (territorio) = 85, menos 20 = 65, pero el tope es 29
        p = proceso("mantenimiento de variador de velocidad y cable electrico", departamento_entidad="Santander")
        r = evaluar(p, umbral=5)
        self.assertEqual(r["puntaje"], 29)
        self.assertEqual(r["nivel"], "revisar")
        self.assertIn("mantenimiento o reparacion: es servicio, no suministro", r["notas"])

    def test_mantenimiento_nunca_llega_a_alerta(self):
        p = proceso("mantenimiento de variador de velocidad y cable electrico", departamento_entidad="Santander")
        self.assertIsNone(evaluar(p))   # el umbral de alerta es 30 y el tope 29

    def test_si_compra_bienes_no_se_penaliza(self):
        r = evaluar(proceso("suministro de variador de velocidad para mantenimiento"))
        self.assertEqual(r["puntaje"], 40)
        self.assertNotIn("mantenimiento o reparacion: es servicio, no suministro", r["notas"])

    def test_suministro_e_instalacion_si_se_penaliza(self):
        # «suministro e instalacion» no esta entre las excepciones a proposito
        r = evaluar(proceso("mantenimiento con suministro e instalacion de plc"), umbral=5)
        self.assertEqual(r["puntaje"], 20)


class UnionTemporal(unittest.TestCase):
    def test_obra_se_marca_resta_pero_no_se_descarta(self):
        r = evaluar(proceso("variador de velocidad y cable electrico", tipo_de_contrato="Obra"))
        self.assertTrue(r["requiere_aliado"])
        self.assertEqual(r["puntaje"], 55)    # 70 - 15
        self.assertIn("incluye obra o montaje, requiere aliado instalador", r["notas"])

    def test_termino_de_montaje_tambien_marca(self):
        self.assertTrue(evaluar(proceso("variador de velocidad y cable electrico con montaje en sitio"))["requiere_aliado"])

    def test_obra_con_aliado_que_queda_corta_cae_en_por_revisar_no_desaparece(self):
        # 40 - 15 = 25: no llega al umbral de alerta (30), pero con el umbral de revision sigue visible
        p = proceso("plc con montaje en sitio")
        self.assertIsNone(evaluar(p))
        r = evaluar(p, umbral=5)
        self.assertEqual((r["puntaje"], r["nivel"], r["requiere_aliado"]), (25, "revisar", True))

    def test_sin_obra_ni_montaje_no_marca(self):
        self.assertFalse(evaluar(proceso("plc"))["requiere_aliado"])

    def test_si_la_empresa_instala_no_marca_nota_ni_resta(self):
        perfil = copy.deepcopy(PERFIL)
        perfil["modalidad_participacion"]["obra_con_instalacion"] = True
        r = radar.evaluar(proceso("plc con montaje"), perfil, copy.deepcopy(FILTROS))
        self.assertEqual(r["puntaje"], 40)
        self.assertNotIn("incluye obra o montaje, requiere aliado instalador", r["notas"])


class Resultado(unittest.TestCase):
    def test_trae_los_campos_que_usa_el_panel(self):
        r = evaluar(proceso(entidad="ESSA", referencia_del_proceso="REF-1", id_del_proceso="CO1.NTC.123",
                            urlproceso={"url": "https://community.secop.gov.co/x"},
                            fecha_de_publicacion_del="2026-10-01T00:00:00.000",
                            proveedores_unicos_con="3"))
        for campo in ("id", "puntaje", "nivel", "requiere_aliado", "entidad", "departamento", "referencia",
                      "descripcion", "modalidad", "tipo_contrato", "valor_cop", "fecha_publicacion",
                      "fecha_cierre", "respondieron", "url", "coincidencias", "notas"):
            self.assertIn(campo, r)
        self.assertEqual(r["fecha_publicacion"], "2026-10-01")
        self.assertEqual(r["respondieron"], 3)
        self.assertEqual(r["valor_cop"], 50_000_000)

    def test_respondieron_es_none_si_secop_no_lo_trae(self):
        self.assertIsNone(evaluar(proceso())["respondieron"])
        self.assertIsNone(evaluar(proceso(proveedores_unicos_con=""))["respondieron"])

    def test_url_no_https_se_descarta(self):
        self.assertEqual(evaluar(proceso(urlproceso="http://inseguro.co"))["url"], "")

    def test_la_descripcion_no_repite_el_nombre(self):
        r = evaluar(proceso("Suministro de plc para planta", nombre_del_procedimiento="Suministro de plc"))
        self.assertEqual(r["descripcion"], "Suministro de plc para planta")

    def test_descripcion_se_corta_a_400(self):
        self.assertEqual(len(evaluar(proceso("plc " + "x" * 1000))["descripcion"]), 400)

    def test_coincidencias_sin_repetir_y_ordenadas(self):
        r = evaluar(proceso("plc, cable electrico y variador de velocidad"))
        self.assertEqual(r["coincidencias"], sorted(set(r["coincidencias"])))


class HoraDeColombia(unittest.TestCase):
    """En la nube el reloj va en UTC; el «hoy» del motor debe ser el de Colombia (UTC-5)."""

    def test_ahora_es_utc_menos_5(self):
        self.assertEqual(radar.ahora().utcoffset(), timedelta(hours=-5))

    def test_cierre_de_hoy_no_se_descarta_de_noche(self):
        # 8:00 p. m. en Colombia = 01:00 UTC del dia siguiente
        noche = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc).astimezone(radar.COLOMBIA)
        self.assertEqual(noche.strftime("%Y-%m-%d"), "2026-10-03")
        with mock.patch.object(radar, "ahora", return_value=noche):
            self.assertIsNotNone(evaluar(proceso(fecha_de_recepcion_de="2026-10-03T23:00:00.000")))
            self.assertIsNone(evaluar(proceso(fecha_de_recepcion_de="2026-10-02T23:00:00.000")))


class DescargaSinRepetidos(unittest.TestCase):
    def test_un_proceso_corrido_de_pagina_no_se_repite(self):
        def fila(i):
            return {"id_del_proceso": f"CO1.NTC.{i}"}
        paginas = {0: [fila(1), fila(2), fila(3)], 3: [fila(3), fila(4), {"id_del_proceso": ""}, {"id_del_proceso": ""}]}

        def falso(parametros, cabeceras, *a, **k):
            if "count(*) as n" in parametros["$select"]:
                return [{"n": "6"}]
            return paginas[parametros["$offset"]]

        with mock.patch.object(radar, "_pedir_pagina", side_effect=falso), mock.patch.object(radar, "TAMANO_PAGINA", 3):
            _, _, gen = radar.recorrer_secop(7)
            ids = [p["id_del_proceso"] for pag in gen for p in pag]
        self.assertEqual(ids, ["CO1.NTC.1", "CO1.NTC.2", "CO1.NTC.3", "CO1.NTC.4", "", ""])   # sin id no se puede comparar: se conservan


class RealConfig(unittest.TestCase):
    """Que la configuracion real y los datos de ejemplo sigan funcionando de punta a punta."""

    def test_los_datos_de_ejemplo_se_evaluan_sin_error(self):
        perfil, filtros = radar.cargar_config()
        resultados = [radar.evaluar(p, perfil, filtros) for p in radar.cargar_demo()]
        alertas = [r for r in resultados if r]
        self.assertTrue(alertas, "ningun proceso de ejemplo genero alerta")
        for r in alertas:
            self.assertTrue(0 <= r["puntaje"] <= 100)
            self.assertIn(r["nivel"], ("alta", "media", "revisar"))
            self.assertTrue(r["coincidencias"])

    def test_la_configuracion_tiene_lo_que_el_motor_espera(self):
        perfil, filtros = radar.cargar_config()
        for clave in ("incluir", "excluir", "puntaje", "niveles"):
            self.assertIn(clave, filtros)
        for grupo in filtros["incluir"].values():
            self.assertGreater(grupo["peso"], 0)
            self.assertTrue(grupo["terminos"])
        self.assertLess(filtros["puntaje"]["umbral_revisar"], filtros["puntaje"]["umbral_alerta"])
        self.assertIn("territorio_prioritario", perfil)

    def test_el_tope_de_mantenimiento_deja_el_proceso_bajo_el_nivel_media(self):
        _, filtros = radar.cargar_config()
        tope = filtros["ajustes_contrato"]["mantenimiento"]["tope_puntaje"]
        self.assertLess(tope, filtros["niveles"]["media"])

    def test_ningun_termino_de_inclusion_esta_tambien_excluido(self):
        _, filtros = radar.cargar_config()
        incluidos = {radar.normalizar(t) for g in filtros["incluir"].values() for t in g["terminos"]}
        excluidos = {radar.normalizar(t) for t in filtros["excluir"]}
        self.assertFalse(incluidos & excluidos)


if __name__ == "__main__":
    unittest.main()
