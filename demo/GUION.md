# Guion de la demo en vivo

Duración total: ~4 minutos de scripts + el tiempo que hables encima. Todo corre en la terminal, sin PowerPoint.

```powershell
cd C:\Users\Joshua\Proyectos\prototipo_mype
powershell -ExecutionPolicy Bypass -File demo\run_all.ps1
```

Cada paso espera un `Enter`. Para que corra sin pausas (ensayo o grabación): `$env:DEMO_SIN_PAUSA="1"`.
Para que vaya más rápido: `$env:DEMO_RAPIDO="1"`.

---

## 1. `01_dataset.py` — “de dónde salen los datos”

**Qué se ve:** el generador crea 18.250 tickets, los tres CSV, y una copia en SQLite que se consulta con SQL.

**Qué dices:**
> “El punto de partida son 12 meses de ventas de un minimarket. Cada ticket tiene su detalle de líneas, y cada línea un SKU y una cantidad. Eso da 127.750 líneas.”

**Qué señalas:**
- La tabla de volúmenes (SKUs, tickets, líneas, anónimos).
- El `insert` a SQLite y las tres consultas: top de productos, venta por mes, quiebres.

**Frase de cierre:**
> “Esto no es un Excel: es la capa de datos que alimenta el entrenamiento. Los modelos no leen la base en vivo, leen estos archivos.”

**Si preguntan si los datos son reales:** “No. Es una simulación calibrada; los parámetros están en `generate_demo.py` y la comparación con el informe está en `RESULTADOS.md`.”

---

## 2. `02_split.py` — “cómo se parte 9 / 2 / 1”

**Qué se ve:** cada mes asignado a entrenamiento, validación o prueba, la línea de tiempo y la verificación de que no hay solapamiento.

**Qué dices:**
> “No se baraja al azar. Con series de tiempo, si validas con marzo y entrenas con octubre, el modelo ya vio el futuro. Eso se llama fuga temporal.”

**Qué señalas:**
- La tabla mes → conjunto.
- La línea de tiempo de colores.
- El `[OK] Sin fuga temporal`.
- Las filas que ve el modelo: 7.848 de entrenamiento, 1.962 de validación, 654 de prueba.

**Detalle fino (te hace ver bien):**
> “9 meses de calendario son 39 semanas, pero las primeras tres se pierden como calentamiento: los rezagos de 4 y 8 semanas todavía no existen. Por eso entrenamiento arranca a fines de noviembre.”

---

## 3. `03_xgboost.py` — “así aprende XGBoost”

**Qué se ve:** la curva de RMSE por ronda, el efecto de agregar más historia, la importancia de variables, el clasificador de quiebre y una predicción real.

**Qué dices:**
> “XGBoost no aprende de golpe: construye árboles en serie y cada uno corrige el error del anterior. Mira cómo baja el RMSE en las primeras 100 rondas y luego se aplana.”

**Qué señalas:**
- La curva: ronda 1, 100, 300, 600.
- El bloque “con 10 semanas vs 36 semanas”: **el error baja 2,6 puntos**.
- La importancia: `media_hist` 60 %, luego `ma_4`, `feriado_next`, `promo_*`.

**Si preguntan “¿por qué media_hist pesa tanto?”:**
> “Porque el mejor predictor de lo que venderás es tu propio nivel histórico de venta. El resto de variables corrige ese nivel: si hay promoción, si es feriado, si la semana pasada subió.”

**Cierre:**
> “El mismo XGBoost, con otra salida, se usa para riesgo de quiebre: en vez de unidades, devuelve probabilidad. Se elige el umbral en validación, no en prueba.”

---

## 4. `04_kmeans.py` — “así se agrupan los clientes”

**Qué se ve:** silueta por k, centroides moviéndose, un plano ASCII con 1.248 clientes y la tabla de segmentos.

**Qué dices:**
> “K-Means no sabe quién es el cliente; solo ve cinco números: frecuencia, gasto, ticket, compras de fin de semana y compras en promoción. Estandarizamos para que el gasto no aplaste al resto.”

**Qué señalas:**
- La tabla de k: por qué k=4 (aunque k=2 tenga mejor silueta).
- Las iteraciones: los centroides se mueven y se asientan.
- El plano: cuatro nubes separadas, 84 % de varianza en dos dimensiones.
- La tabla final: Hogar 40 %, Ocasional 28 %, Promo-sensible 20 %, Mayorista 12 %.

**Cierre:**
> “El algoritmo agrupa; la interpretación la pone el negocio. Cada segmento termina en una acción concreta de promoción.”

---

## 5. `05_alertas.py` — “del modelo a la decisión”

**Qué se ve:** probabilidad por SKU, reglas de decisión, el plan A* semana a semana y el JSON que consume el front.

**Qué dices:**
> “Aquí se junta todo. El modelo de demanda dice cuánto se va a vender; el de quiebre, qué tan probable es que falte. Con el stock y la cobertura salen cuatro decisiones.”

**Qué señalas:**
- Las cuatro reglas impresas (REPONER / REVISAR / NO COMPRAR / MANTENER).
- La tabla con el color de cada acción.
- El plan A* de tres SKUs: pedido, stock final y costo por semana.
- El JSON: “esto es literalmente lo que pinta el dashboard”.

**Si preguntan “¿de dónde sale el costo?”:**
> “La función objetivo suma almacenamiento, costo fijo de pedido, faltante y merma. A* explora combinaciones de pedido y se queda con la de menor costo acumulado.”

---

## 6. `06_publicar.py` — “y el panel lo refleja” (opcional, ~1 min)

**Qué se ve:** entrena el pipeline completo, imprime la tabla objetivo vs logrado y confirma que la API está en línea.

**Qué dices:**
> “Este es el mismo entrenamiento, pero completo: cinco modelos de demanda, cinco de quiebre y el clustering con ARI. Al terminar, los artefactos cambian y la API los recarga sola.”

Luego abre `http://127.0.0.1:8080` y muestra:
- Panel con KPIs y la tabla de modelos.
- Pronóstico ordenado por demanda.
- Segmentos y plan de compra.
- Botón **Sincronizar alertas**.

---

## Preguntas probables

**“¿Esto es machine learning de verdad?”**
> “Sí: XGBoost con objetivo Poisson para conteos, búsqueda de hiperparámetros solo en validación, y K-Means con selección de k por silueta. Lo que es simulado son los datos.”

**“¿Por qué XGBoost y no una red neuronal?”**
> “Datos tabulares, 25 variables, 7.848 filas. Un árbol con boosting rinde mejor y se explica; una red no aporta y no se puede justificar al dueño de la tienda.”

**“¿Cómo sé que no hay fuga?”**
> “Mira el paso 2: todo entrenamiento termina antes de que empiece validación, y validación antes de prueba. Además hay un test que recalcula `ma_4` y `lag_1` a mano y exige que coincidan.”

**“¿Y si el negocio cambia?”**
> “Se reentrena con la ventana móvil; el paso 3 muestra justamente el efecto de agregar semanas. El monitoreo de deriva compara la distribución de entrada con PSI.”

**“¿Por qué los números no son idénticos al informe?”**
> “Porque el informe se escribió antes de ejecutar esto. La tabla de calibración muestra el desvío de cada métrica; lo que no se puede medir (NPS, sobre-stock, latencia) está marcado como pendiente en `RESULTADOS.md`.”
