"""El ejemplo de la pestaña Criterios debe dar el mismo puntaje que el motor de verdad."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import radar  # noqa: E402
import servidor  # noqa: E402


class EjemploDeCriterios(unittest.TestCase):
    def test_el_ejemplo_coincide_con_el_motor(self):
        perfil, filtros = radar.cargar_config()
        _, ejemplo = servidor._ajustes_y_ejemplo(perfil, filtros)
        proceso = {
            "descripci_n_del_procedimiento": f"Suministro de {ejemplo['objeto']} para una planta",
            "nombre_del_procedimiento": "",
            "departamento_entidad": "Santander",
            "tipo_de_contrato": "Compraventa",
            "modalidad_de_contratacion": "Mínima cuantía",
            "estado_de_apertura_del_proceso": "Abierto",
            "precio_base": "80000000",
        }
        r = radar.evaluar(proceso, perfil, filtros)
        self.assertIsNotNone(r)
        self.assertEqual(r["puntaje"], ejemplo["total"])

    def test_los_ajustes_traen_puntos_y_texto(self):
        perfil, filtros = radar.cargar_config()
        ajustes, _ = servidor._ajustes_y_ejemplo(perfil, filtros)
        self.assertTrue(ajustes)
        for a in ajustes:
            self.assertTrue(a["texto"])
            self.assertNotEqual(a["puntos"], 0)


if __name__ == "__main__":
    unittest.main()
