# Snapshot-Laya

Interfaz local para identificar **controles renderizados de juegos demo**, sin
analizar apuestas históricas ni enviar un HAR entero al modelo.

HardFire obtiene el árbol de controles y sus rectángulos de interacción. El filtro
retiene los controles relevantes y Laya multilingüe, ejecutado con ONNX/DirectML,
propone una función. La captura y los recortes permiten revisar esa propuesta.

## Iniciar en esta PC

Abrir **Iniciar Snapshot Laya.cmd**. La aplicación escucha únicamente en
<http://127.0.0.1:18766> y utiliza el entorno de Laya ya instalado.

1. Mantener HardFire abierto con su servidor MCP local.
2. Agregar una o varias URLs oficiales de demos de Pragmatic Play.
3. Abrir la primera demo y resolver cualquier aviso que cubra el juego.
4. Revisar las clasificaciones y la captura; elegir una función cuando Laya esté
   inseguro, marcar la revisión visual y ejecutar el control actual.
5. Observar los nuevos botones al abrir menús, compras y opciones de bonus.
6. **Validar y cerrar** exige completar los controles observados y, si hubo
   compras, comprobar que el protocolo y la ronda hayan finalizado.
7. **Cerrar incompleto** conserva lo encontrado sin certificarlo. Si hay otra demo
   en la cola, se abre después de guardar y cerrar la sesión actual.

El modo manual conserva la revisión visual. **Explorar ramas** usa la primera URL
y separa la interfaz común de las decisiones del juego. Las firmas conocidas
reciben función directa; los botones nuevos pueden recorrerse como `probe`
aunque Laya no conozca su nombre. Deben estar dibujados, dentro del juego y
tener una acción guiada vigente. La propuesta semántica de Laya se conserva
separada del efecto comprobado.

## Recorrer ramas

El análisis OCR de Playtech aplica `common_ui_v1` antes de Laya: separa saldo,
apuesta normal, moneda, win, líneas, autoplay, turbo, ayuda, sonido y cabecera.
El giro queda en apoyo para ante bet y no se envía al clasificador. Las compras,
extra bet, confirmaciones y continuaciones tienen prioridad sobre esas reglas.
Los textos desconocidos se conservan aparte, sin declararlos interfaz común.
Se unen etiquetas contiguas como BUY + FEATURE y descripciones de un mismo
interruptor. Este filtro actúa sobre metadatos OCR, no borra zonas de la imagen.

`POST /api/providers/playtech/filter` recibe `{snapshot, stage, game_name}`;
`snapshot` contiene `width`, `height` y `lines: [{text, rect: {x,y,width,height}}]`.
`POST /api/providers/playtech/analyze` aplica el filtro y clasifica únicamente
los candidatos usando la misma instancia de Laya del servidor. Ninguna de estas
rutas hace clic ni considera que una caja de texto sea un collider verificado.

Desde 0.3.2, un juego listo y estable sin controles objetivo guarda captura y HAR
y termina con `no_target_controls_detected`. Esto describe la interfaz visitada:
no certifica que el juego carezca de compras en todos sus estados. Si solo hay
ante bet se guarda también una captura y se comprueban sus tiradas normalmente.
Los selectores Zeus/Hades tienen una excepción de cambio solo de color ante
`QUIET_TIMEOUT`: se registran como `selection_exception`, sin repetir el clic ni
contarlos como una compra o efecto verificado. Otros fallos conservan el bloqueo.

El catálogo de Playtech está en `/playtech` y `/api/providers/playtech/catalog`.
Se importó la categoría oficial Slots guardada por Tester-Spin el 18/10/2026,
con 526 juegos. Usa el lanzamiento directo de ese repositorio, con `real=0` y
`preferedmode=offline`; la disponibilidad se comprueba al abrir cada juego.
Amazon Wild cargó en modo «PLAYING FOR FUN». El catálogo web tiene cookies y
verificación de edad, y su botón Play puede solicitar acceso; el lanzamiento
directo evita depender de ese recorrido. El adaptador de extracción y exploración
de controles de Playtech todavía no está implementado: no se reutiliza el de
Pragmatic ni se certifican sus compras por abrir la demo.

Desde 0.3.2, un juego listo y estable sin controles objetivo guarda captura y HAR
y termina con `no_target_controls_detected`. Esto describe la interfaz visitada:
no certifica que el juego carezca de compras en todos sus estados. Si solo hay
ante bet se guarda también una captura y se comprueban sus tiradas normalmente.
Los selectores Zeus/Hades tienen una excepción de cambio solo de color ante
`QUIET_TIMEOUT`: se registran como `selection_exception`, sin repetir el clic ni
contarlos como una compra o efecto verificado. Otros fallos conservan el bloqueo.

El catálogo de Playtech está en `/playtech` y `/api/providers/playtech/catalog`.
Se importó la categoría oficial Slots guardada por Tester-Spin el 18/10/2026,
con 526 juegos. Usa el lanzamiento directo de ese repositorio, con `real=0` y
`preferedmode=offline`; la disponibilidad se comprueba al abrir cada juego.
Amazon Wild cargó en modo «PLAYING FOR FUN». El catálogo web tiene cookies y
verificación de edad, y su botón Play puede solicitar acceso; el lanzamiento
directo evita depender de ese recorrido. El adaptador de extracción y exploración
de controles de Playtech todavía no está implementado: no se reutiliza el de
Pragmatic ni se certifican sus compras por abrir la demo.

El descubrimiento inicial guarda compras y ante bet y sigue una opción en la
sesión actual. Al descubrir un menú, guarda todas las opciones y continúa por
una sin cerrar el juego. Las opciones restantes quedan pendientes; para volver
a ellas abre una sesión demo nueva y reproduce su prefijo con snapshots nuevos.
Un menú con cuatro compras genera
cuatro caminos; las confirmaciones y cancelaciones descubiertas agregan ramas.
Los menús se consideran explorados cuando sus siguientes decisiones se guardan;
las ramas de confirmación exigen terminar la compra y el bonus.

Ante bet requiere comprobar OFF → ON y **dos tiradas normales**, cada una con
inicio reconocido, protocolo completo y el mismo nivel de ante bet activo antes
y después. El botón de giro solo se usa como apoyo de esta prueba. Subir y bajar
la apuesta regular quedan fuera del recorrido.

Las continuaciones conocidas incluyen áreas de «click/tap anywhere to continue»
cuando el extractor devuelve un collider con ese texto y contexto. Un bloqueador
genérico no equivale a una continuación. Los controles nuevos con interacción
verificada se agregan al árbol. Si abren otro menú se guardan sus siguientes
ramas; si inician una operación se espera su protocolo y bonus. Si aparecen
varias opciones dentro del bonus, prueba una en la sesión actual y reproduce el
prefijo en sesiones nuevas para las restantes. Los nodos que compartieron sesión
comparten el informe y HAR crudo, guardado al cerrar esa sesión.
Un nodo `expanded` solo cuenta en la cobertura
completa cuando sus descendientes también están comprobados.

No se exploran controles de la interfaz común, coordenadas sin collider, ni
controles sin acción guiada. Un clic sin efecto comprobado sigue deteniendo la
rama; no hay reintentos silenciosos de compras.

El panel permite pausar y continuar. Se guardan caminos y evidencias en
`runs/branches.json`; al reiniciar, una rama que estaba ejecutándose queda
interrumpida y no se repite silenciosamente. Una compra sin efecto comprobado,
un cambio de identidad o una interacción no verificable detienen el recorrido.
Se esperan dos observaciones con los mismos controles semánticos. Las animaciones
pueden cambiar sus rectángulos: se resuelven geometría y token nuevos antes del
clic y se exige que coincidan identidad y firma. La revisión manual conserva su
rechazo de cambios geométricos. Los límites son 60 ramas, profundidad 10 y 300 segundos por rama;
alcanzarlos deja pendientes, nunca certifica cobertura completa.

Cada cierre conserva el HAR crudo de HardFire, sin reproducir solicitudes. El
informe de ramas y los HAR de las sesiones se pueden descargar desde el panel.
Solo se resuelve automáticamente el aviso de edad conocido para este operador,
que ya confirmó su mayoría de edad; otros avisos requieren intervención.

## Requisitos y configuración

- Windows, Python 3.11 o superior y ONNX Runtime DirectML.
- HardFire con `pragmatic_guided_*`, `pragmatic_drawn_buttons`, `hardfire_find`,
  `hardfire_click_ref` y `hardfire_click_relative` en su MCP local.
- Checkpoint multilingüe original y `multilingual-directml.onnx`, con sus datos
  externos, en el directorio de modelos de Laya.

```powershell
python -m pip install -e .
python -m snapshot_laya
```

Variables opcionales:

| Variable | Valor por defecto |
|---|---|
| `LAYA_MODEL_DIR` | `%USERPROFILE%/Documents/Codex/Laya/models` |
| `HARDFIRE_MCP_URL` | `http://127.0.0.1:8765/mcp` |
| `SNAPSHOT_LAYA_PORT` | `18766` |
| `SNAPSHOT_LAYA_DATA` | `runs` |
| `SNAPSHOT_LAYA_PYTHON` | Intérprete que usa el lanzador de Windows |

Los pesos no se incluyen en Git. Esta aplicación usa el grafo ONNX compatible con
DirectML instalado previamente; no exporta ni descarga modelos al arrancar.

## Qué entra al modelo

Primero se filtran firmas conocidas de la interfaz con un catálogo versionado;
esto no modifica los pesos de Laya. Solo los controles desconocidos se envían al
modelo: etiquetas, nombre, ruta interna, sprites y eventos.
El panel muestra «firma conocida» para el catálogo, sin asignarle un porcentaje
de confianza inventado. Los porcentajes se reservan para las propuestas de Laya.
Las coordenadas y las imágenes se conservan como evidencia, no se inventan con
Laya. Se descartan controles sin hit target, deshabilitados, fuera de pantalla,
duplicados y elementos comunes de sonido, autoplay, velocidad y ajustes.

Los avisos DOM activos bloquean la clasificación. En la pantalla completa propia
del proveedor se aísla el aviso de edad de la página que queda detrás, solo si
el contenedor cubre el viewport, el juego ya puede girar y el aviso no está dentro
de ese contenedor. Otros avisos siguen bloqueando. Los menús modales conocidos
eliminan los controles de fondo. **La oclusión genérica no está verificada**.
Se comprueban otra vez identidad, geometría y
estado antes del clic, y se conservan los tokens de observación de HardFire.

El giro normal se conserva en `support_controls` para ante bet y no se envía al
modelo ni se presenta como una rama. La interfaz común queda en `ignored_controls`;
solo los controles objetivo aparecen en `controls` y llegan a Laya si son nuevos.

Durante un bonus se pueden diferir diagnósticos `NO_VERIFIED_VISIBLE_DRAWING`
solo si su ruta corresponde exactamente a una compra ya descubierta en el
fondo. Se conservan en la evidencia y no se tocan esos controles. Al volver al
estado de reposo los diagnósticos deben desaparecer; otros controles sin resolver
mantienen el bloqueo. El botón de detener giro es auxiliar y no se explora.

## Qué significa validado

`validated_observed_scope` significa que los controles registrados tienen efectos
comprobados y no queda una ronda, compra, bloqueo o control pendiente en los
estados visitados. **No demuestra cobertura exhaustiva del juego**, de estados no
visitados ni de todas las combinaciones de apuesta. El modelo tampoco está
calibrado para cada juego: una confianza alta puede ser incorrecta.

La aplicación no oculta los errores de Laya. En la prueba inicial de Sweet Bonanza
reconoció la compra, giro y dirección de apuesta, pero confundió el control de
double chance con un cambio de apuesta de baja confianza. Ese caso requiere
corrección del operador. Ver `docs/live-checks.json` para evidencia medida.

Los informes JSON se guardan en `runs/` y se descargan desde el panel. HardFire
conserva por separado sus capturas, traza y HAR. Esos artefactos privados no se
suben al repositorio. Solo se cierran sesiones que abrió esta aplicación.

## Verificación

```powershell
python -m unittest discover -s tests
```

Las pruebas cubren filtros, modales, snapshots obsoletos, cambios previos al clic,
protocolo pendiente, bonus activo, cierre incompleto y propiedad de sesiones.
Los tests no abren juegos ni realizan compras.
