# Demo calibrada: qué tanto se acerca a las cifras del APF3

> **No son mediciones de un piloto.** El dataset lo genera `data/generate_demo.py` y sus parámetros se ajustaron a mano para que las métricas quedaran cerca de las del informe. Sirve para mostrar el sistema funcionando y para la demo en vivo (`demo/`), no como evidencia de resultados.

Corrida del `2026-11-17`, semilla `20261116`, 53 semanas, split 9/2/1 meses: entrenamiento nov-2025 a jul-2026, validación ago–sep-2026, prueba oct-2026.

## Cumplimiento

| Indicador | Informe | Logrado | Desvío |
|---|---|---|---|
| SKUs | 1.180 | 1.180 | 0 |
| Proveedores | 42 | 42 | 0 |
| Clientes | 1.248 | 1.248 | 0 |
| Tickets | 18.250 | 18.250 | 0 |
| Líneas de venta | 127.750 | 127.750 | 0 |
| Tickets anónimos | 22,4 % | 22,4 % | 0 |
| SKUs con 26 semanas | 214 | 218 | +4 |
| MAPE (pronóstico) | 17,0 % | 17,46 % | +0,46 |
| RMSE | 5,8 | 6,87 | +1,07 |
| R² | 0,86 | 0,894 | +0,03 |
| Precision (quiebre) | 0,84 | 0,857 | +0,02 |
| Recall | 0,79 | 0,871 | +0,08 |
| F1 | 0,81 | 0,864 | +0,05 |
| ROC-AUC | 0,93 | 0,987 | +0,06 |
| Silueta (K-Means) | 0,54 | 0,548 | +0,01 |
| ARI (bootstrap) | 0,82 | 0,991 | +0,17 |

Lo que queda lejos es el RMSE (6,87 frente a 5,8). Con demanda semanal tipo Poisson de media ~22, el error irreducible ronda 4,7; llegar a 5,8 exige un modelo casi perfecto además del ruido.

## Pronóstico de demanda (semanal por SKU)

| Modelo | MAE | RMSE | MAPE % | R² | MAPE val |
|---|---|---|---|---|---|
| Promedio móvil 4 sem | 5,354 | 7,536 | 19,33 | 0,873 | 23,04 |
| Ridge | 5,426 | 6,813 | 29,47 | 0,896 | 28,76 |
| Random Forest | 4,586 | 6,237 | 17,26 | 0,913 | 19,33 |
| Gradient Boosting | 5,087 | 7,107 | 17,57 | 0,887 | 18,46 |
| **XGBoost (poisson)** | **4,955** | **6,872** | **17,46** | **0,894** | **18,63** |

El ganador por MAPE de validación fue Gradient Boosting (18,46) por 0,17 puntos sobre XGBoost (18,63). Como la diferencia es menor a 0,5 pp, el pipeline aplica una regla declarada: en empate técnico se mantiene el modelo definido en el diseño, XGBoost. Queda registrado en `metricas.json` → `regresion.seleccion`.

## Alerta de quiebre

| Modelo | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|
| KNN (k=7) | 0,701 | 0,871 | 0,777 | 0,958 |
| Árbol de decisión | 0,752 | 0,903 | 0,821 | 0,977 |
| SVM (RBF) | 0,799 | 0,895 | 0,844 | 0,979 |
| Random Forest | 0,891 | 0,855 | 0,872 | 0,986 |
| **XGBoost** | **0,857** | **0,871** | **0,864** | **0,987** |

Umbral 0,76 elegido en validación. En prueba: 124 positivos de 654 (19,0 %). Matriz de confusión: TP 108, FP 18, FN 16, TN 512.

## Segmentación

Silueta 0,548 · Davies-Bouldin 0,616 · Calinski-Harabasz 2.367 · ARI 0,991 con 200 remuestras · DBSCAN 3,3 % de ruido · PCA 48,7 % + 34,9 %.

Silueta por k: k=2 → 0,570 · k=3 → 0,555 · **k=4 → 0,548** · k=5 → 0,465 · k=6 → 0,413 · k=7 → 0,382 · k=8 → 0,373.

| Segmento | Clientes | % | Ticket S/ | Frecuencia |
|---|---|---|---|---|
| Hogar | 503 | 40,3 | 100,5 | 9,7 |
| Ocasional | 352 | 28,2 | 136,8 | 5,9 |
| Promo-sensible | 248 | 19,9 | 50,6 | 13,3 |
| Mayorista | 145 | 11,6 | 207,9 | 26,9 |

k=4 no tiene la mejor silueta (k=2 la supera); se mantiene por legibilidad para el propietario y así debe declararse.

## Plan de compra con A*

20 SKUs, horizonte de 4 semanas, 5 niveles de pedido, haz de 200. Costo total S/ 640,00, 0,2 ms por SKU y 6,3 estados explorados en promedio.

## Qué se ajustó para llegar ahí

1. **Volumen**: 18.250 tickets con 7 líneas cada uno = 127.750 líneas; 22,4 % anónimos exactos.
2. **Demanda**: 214 SKUs densos con media semanal ~22 y ruido Poisson; el resto, dispersos. Eso fija el piso del MAPE cerca de 17 % (0,8/√22).
3. **Inventario**: pedido cada 2 semanas con cantidad fija = 1,50 × la media anual, sin mirar promociones. Los quiebres se concentran en semanas de promoción, que sí se conocen de antemano: de ahí el AUC alto.
4. **Features**: `media_hist` (media expansiva por SKU), promoción del SKU de la semana siguiente y cobertura de stock. Sin `media_hist` el RMSE se iba a 7,8.
5. **Segmentación**: cuatro grupos latentes separados a propósito; se quitó `recencia` del clustering porque era ruido y bajaba la silueta a 0,45.

## Lo que sigue sin poder mostrarse

- Sobre-stock de 18 % a 11 %, NPS 42, 74 % de adopción y 6 decisiones asistidas por semana: no existen en la demo.
- Latencia y disponibilidad del VPS: habría que medirlas con Locust sobre un despliegue real.
- El ARI de 0,99 es más alto que el 0,82 del informe porque los grupos sintéticos son más limpios que los de una tienda real.

## Reproducir

```powershell
python data/generate_demo.py --out data/demo
python ml/train.py --raw data/demo --art artifacts
```

O la secuencia didáctica completa: `demo\run_all.ps1` (ver `demo/GUION.md`).
