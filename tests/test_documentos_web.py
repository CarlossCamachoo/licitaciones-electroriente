"""Version de solo estado de los documentos para la web compartida."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import documentos


class TestEstadoWeb(unittest.TestCase):
    def test_resumen_valido_acepta_ids_y_fechas(self):
        self.assertEqual(documentos.resumen_valido({"rut": ["", "2027-01-31"]}), {"rut": ["", "2027-01-31"]})

    def test_resumen_valido_rechaza_lo_raro(self):
        for malo in ([], {"inventado": [""]}, {"rut": "2027-01-31"}, {"rut": ["31/01/2027"]}):
            with self.assertRaises(ValueError):
                documentos.resumen_valido(malo)

    def test_sin_archivos_todo_falta(self):
        cats = documentos.listar_desde({})
        estados = {d["estado"] for c in cats for d in c["documentos"]}
        self.assertEqual(estados, {"falta"})

    def test_estado_por_fecha_y_sin_datos_privados(self):
        hoy = documentos.hoy_colombia()
        resumen = {"rut": [""], "rup": [date(2000, 1, 1).isoformat()]}
        docs = {d["id"]: d for c in documentos.listar_desde(resumen) for d in c["documentos"]}
        self.assertEqual(docs["rut"]["estado"], "listo")
        self.assertEqual(docs["rup"]["estado"], "vencido")
        self.assertTrue(hoy.year >= 2026)
        for d in docs.values():
            for a in d["archivos"]:
                self.assertEqual(set(a), {"vence", "estado"})


if __name__ == "__main__":
    unittest.main()
