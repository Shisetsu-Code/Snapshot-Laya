# Recorrido por snapshots

Objetivo: descubrir compras y confirmaciones, volver a abrir la demo para cada rama y comprobar ante bet con dos tiradas normales activas. Solo controles de catálogo con acción guiada vigente se ejecutan automáticamente. Laya conserva los desconocidos para revisión; no se consideran resueltos por confianza alta.

1. Catálogo conservador y filtro de ventanas/bloqueadores; mantener girar solo como apoyo de ante bet.
2. Cola persistida de caminos semánticos, reproducidos sobre snapshots nuevos. Una sesión aislada por camino; límites de ramas, profundidad y tiempo dejan pendientes, nunca validan.
3. Ante bet: evidencia de OFF → ON y dos protocolos de tirada completos con el mismo nivel activo. Activación sola no valida.
4. Panel de inicio/pausa/avance y progreso; cierre guarda HAR crudo de HardFire y evidencia sin reproducir solicitudes.
5. Pruebas de catálogo, bifurcaciones, sesiones, ambigüedad, reinicio y protocolos. Prueba demo controlada antes de informar resultados.

Implementado y verificado: 59 pruebas; Gates of Olympus 1000 completó cuatro ramas descubiertas sin intervención en la pasada final. Ante bet exigió dos tiradas con nivel activo, la compra confirmó y terminó su bonus, las continuaciones de entrada y resultado funcionaron, y cancelar regresó al control de compra. HAR crudos guardados y todas las sesiones propias cerradas. Evidencia saneada en `branch-live-check.json`. La cobertura no incluye estados ocultos ni combinaciones arbitrarias.
