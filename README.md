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

El cierre automático es opcional y usa el mismo criterio de validación. No hay
clics autónomos ni repetición automática de compras: cada acción requiere una
elección explícita sobre un control actual. La clasificación del modelo por sí
sola no autoriza acciones.

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

Solo texto del control: etiquetas, nombre, ruta interna, sprites y eventos.
Las coordenadas y las imágenes se conservan como evidencia, no se inventan con
Laya. Se descartan controles sin hit target, deshabilitados, fuera de pantalla,
duplicados y elementos comunes de sonido, autoplay, velocidad y ajustes.

Los avisos DOM bloquean la clasificación. Los menús modales conocidos eliminan
los controles de fondo. **La oclusión genérica no está verificada**: la revisión
visual sigue siendo necesaria. Se comprueban otra vez identidad, geometría y
estado antes del clic, y se conservan los tokens de observación de HardFire.

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
