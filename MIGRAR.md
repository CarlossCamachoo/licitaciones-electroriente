# Pasos para migrar a Claude Code

1. Descomprime o copia esta carpeta donde guardes tus proyectos.

2. Abre una terminal en la carpeta e inicializa git:

   git init
   git add .
   git commit -m "Radar de licitaciones Electroriente, bloque A"

3. Crea el repositorio privado en GitHub y conéctalo:

   git remote add origin git@github.com:TU_USUARIO/licitaciones-electroriente.git
   git branch -M main
   git push -u origin main

4. Instala las dependencias:

   pip install -r requirements.txt

5. Abre Claude Code en la carpeta. Lee CLAUDE.md automáticamente.

6. Lo primero que hay que hacer, la prueba que falta:

   python src/radar.py --dias 7

   Si falla, probablemente sea el nombre de un campo de la API.
   Pídele a Claude Code que lo corrija comparando contra:
   https://www.datos.gov.co/resource/p6dx-8zbt.json?$limit=1

7. Cuando consigas los documentos de la empresa, créalos en una carpeta
   docs/empresa/ y pídele a Claude Code que actualice config/perfil.yaml
   y marque los pendientes resueltos en config/pendientes.yaml.
