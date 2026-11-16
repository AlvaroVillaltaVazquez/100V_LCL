# Limitador de Corriente de Enclavamiento (LCL) Conmutado para Buses de 100 V

[![Institución](https://img.shields.io/badge/UC3M-Grado%20en%20Ingenier%C3%ADa%20Electr%C3%B3nica%20Industrial%20y%20Autom%C3%A1tica-000066)](https://www.uc3m.es/)
[![Licencia](https://img.shields.io/badge/Licencia-CC%20BY--NC--ND%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-nd/4.0/deed.es)
[![Herramientas](https://img.shields.io/badge/EDA%20%26%20Simulaci%C3%B3n-KiCad%20%7C%20PSIM%20%7C%20MATLAB-informational)]()

**Trabajo Fin de Grado (2025–2026)**  
* **Título:** Diseño, modelado e implementación de un circuito conmutado para la protección por sobre-corriente  
* **Autor:** Álvaro Villalta Vázquez    
* **Departamento / Universidad:** Universidad Carlos III de Madrid (UC3M)

---

## 1. Descripción Técnica y Motivación

En los sistemas de distribución de potencia aeroespaciales, la transición desde buses tradicionales de $28\text{ V}$ hacia buses de mayor tensión ($100\text{ V}$) invalida el uso de Limitadores de Corriente de Enclavamiento (**LCL**, *Latching Current Limiters*) clásicos basados en transistores **MOSFET de canal P (P-MOS)** operando en región lineal. Durante un evento de sobrecorriente, el transistor lineal debe absorber prácticamente toda la caída de tensión del bus ($P_{\text{lineal}} \approx V_{\text{bus}} \cdot I_{\text{lim}}$), excediendo rápidamente los límites del Área de Operación Segura (**SOA**) y penalizando críticamente la masa del sistema de gestión térmica.

Este proyecto desarrolla el diseño analítico, simulación con componentes parásitos y prototipado en PCB de un **LCL conmutado basado en un MOSFET de canal N (N-MOS) en configuración *high-side*** (topología reductora/Buck sin condensador de salida). Durante una sobrecorriente, el interruptor conmuta en alta frecuencia dentro de una banda de histéresis controlada durante un tiempo máximo (*trip-off time*) gobernado por una red RC asimétrica con memoria térmica antes de enclavar la desconexión de la carga.

---

## 2. Arquitectura y Parámetros de Diseño

El sistema se divide en cuatro bloques funcionales referenciados a una masa flotante vinculada al surtidor del N-MOS, alimentada mediante un convertidor CC/CC aislado galvánicamente ($+15\text{ V}$) y un regulador lineal auxiliar ($+5\text{ V}$):

1. **Etapa de Potencia y Gate Driver:** N-MOS en *high-side* sin condensador de salida para permitir el control dinámico directo de la corriente a través de la inductancia principal y un diodo de libre circulación Schottky de Carburo de Silicio (SiC).
2. **Sensado y Acondicionamiento:** Medida mediante resistencia *shunt* con conexión Kelvin y amplificación inversora en dos etapas ($G \approx -25\text{ V/V}$) con filtrado paso bajo activo.
3. **Control por Histéresis:** Comparadores analógicos de alta velocidad atacando un biestable RS para mantener la corriente confinada entre $I_{\text{hys,inf}}$ e $I_{\text{hys,sup}}$.
4. **Temporizador Asimétrico con Memoria Térmica:** Red $RC$ con constantes de tiempo diferenciadas de carga y descarga basada en la impedancia térmica transitoria (red de Foster) del semiconductor, reduciendo el tiempo de disparo ante fallos sucesivos.

### Resumen de Especificaciones y Dimensionamiento (Bus de 100 V)

| Parámetro / Bloque | Valor de Diseño | Criterio / Norma de Referencia |
| :--- | :--- | :--- |
| **Tensión nominal del bus ($V_{\text{bus}}$)** | $100\text{ V}$ | Arquitectura de potencia satelital de alta tensión |
| **Corriente de limitación ($I_{\text{lim}}$)** | $3{,}7\text{ A}$ | Umbral de activación del temporizador ($V_{\text{TimON}} = 2{,}035\text{ V}$) |
| **Banda de histéresis ($\Delta i$)** | $3{,}7\text{ A} \text{ -- } 4{,}5\text{ A}$ ($0{,}8\text{ A}$) | Compromiso entre pérdidas de conmutación y retardo de lazo ($t_{\text{sense}} = 171{,}4\text{ ns}$) |
| **Tiempo de disparo ($t_{\text{trip}}$)** | $1{,}5\text{ ms}$ | Criterio más restrictivo adaptado de ECSS-E-ST-20-20C |
| **Memoria térmica ($t_{\text{descarga}}$)** | $63{,}05\text{ ms}$ | Red asimétrica ($C_{\text{timer}} = 100\text{ nF}$, $R_{\text{carga}} = 26{,}1\text{ k}\Omega$, $R_{\text{dis}} = 100\text{ k}\Omega$) |
| **Inductor de potencia ($L$)** | $68\ \mu\text{H}$ | Valor comercial superior a $L_{\text{min}} = 42{,}85\ \mu\text{H}$ (requisitos ECSS 5.4.1.1.1 y 5.2.3.1a) |
| **Frecuencia de conmutación ($f_{\text{sw}}$)** | $614{,}98\text{ kHz}$ | Peor caso operacional ($D = 0{,}5$, $V_{\text{out}} = 50\text{ V}$); límite térmico $f_{\text{sw,max}} \le 2{,}253\text{ MHz}$ |
| **Resistencia de sensado ($R_{\text{shunt}}$)** | $22\text{ m}\Omega$ | Disipación nominal $0{,}301\text{ W}$ y caída de tensión $< 0{,}082\%$ del bus |
| **Filtrado de entrada ($C_{\text{bus}}$)** | $47\ \mu\text{F} \parallel 1\ \mu\text{F}$ | Condensador *bulk* electrolítico + cerámico de baja ESL ($\Delta V_{\text{bus}} = 31{,}3\text{ mV}$) |

---

## 3. Componentes Principales (BOM)

* **MOSFET de potencia (N-MOS):** Infineon `IRFB4020PbF` ($200\text{ V}$, $18\text{ A}$, $R_{\text{DS,ON}} = 80\text{ m}\Omega$, $Q_{\text{G}} = 18\text{ nC}$)
* **Diodo de libre circulación (SiC Schottky):** STMicroelectronics `STPSC6H065B-TR` ($650\text{ V}$, $6\text{ A}$, $Q_{\text{rr}} \approx 0$)
* **Controlador de puerta (*Gate Driver*):** Texas Instruments `UCC27511AQDBVRQ1` ($4\text{ A}$ *source* / $8\text{ A}$ *sink*, salida dividida)
* **Inductor de potencia:** Würth Elektronik `WE-HCI 74435586800` ($68\ \mu\text{H}$, hilo plano, núcleo apantallado, $\text{DCR} = 27{,}3\text{ m}\Omega$)
* **Amplificador operacional:** Texas Instruments `OPA2836QDGKRQ1` ($\text{GBW} = 205\text{ MHz}$, $\text{SR} = 560\text{ V}/\mu\text{s}$, entrada *Negative-Rail*)
* **Comparadores analógicos:** `LM319AM/NOPB` (lazo de histéresis, $t_{\text{resp}} = 70\text{ ns}$) y `LM393BIDR` (temporizador de bajo consumo)
* **Lógica digital:** `SN74LVC2G02DCUR` (doble puerta NOR en configuración biestable RS) y `74LVC1G08QW5-7` (puerta AND)
* **Alimentación flotante:** Traco Power `TMA 1515S` (CC/CC aislado $15\text{ V}$) + STMicroelectronics `L78L05CD13TR` (regulador lineal $5\text{ V}$)

---

## 4. Resultados y Validación

### Simulación Dinámica (PSIM con efectos parásitos)
Se incorporaron los retardos de propagación reales de la cadena de control ($t_{\text{sense}} = 113\text{ ns}$ en el lazo de histéresis), resistencias serie equivalentes (ESR/DCR) y tiempos de conmutación:
* **Cortocircuito permanente ($R_{\text{sc}} = 0{,}1\ \Omega$):** Conmutación estable entre $3{,}708\text{ A}$ y $4{,}465\text{ A}$ durante $\Delta t = 1{,}496\text{ ms}$ (desviación $< 0{,}3\%$ respecto a los $1{,}5\text{ ms}$ teóricos) antes de ejecutar el enclavamiento definitivo.
* **Fallos sucesivos (Memoria térmica):** Ante un segundo transitorio ocurrido antes de completarse los $63{,}05\text{ ms}$ de descarga de $C_{\text{timer}}$, el tiempo de actuación se redujo automáticamente a $\Delta t = 0{,}686\text{ ms}$, protegiendo la unión del MOSFET frente a acumulación térmica.

### Prototipo PCB y Ensayos en Laboratorio (KiCad + Tektronix TPS 2024)
* **Etapa de potencia y filtrado inductivo:** Validada experimentalmente mediante excitación PWM externa ($f_{\text{sw}} \approx 507{,}9\text{ kHz}$, $D \approx 0{,}65$) a tensión reducida ($12{,}2\text{ V}\text{--}14\text{ V}$, $I_{\text{out}} = 1\text{ A}$). La bobina de $68\ \mu\text{H}$ filtró eficazmente la onda pulsada sin condensador de salida, obteniendo una eficiencia experimental del $89{,}2\%$ a baja tensión (frente al $96{,}5\%$ teórico en operación nominal a $100\text{ V}$ y $D = 1$).
* **Errata conocida de hardware (v1.0) y trabajo futuro:** Durante el ensamblaje se detectó una discrepancia de huella en el biestable RS `SN74LVC2G02DCUR` (encapsulado físico `VSSOP-8` de $0{,}5\text{ mm}$ de *pitch* frente a huella `SOIC-8` de $1{,}27\text{ mm}$). La reparación mediante montaje en araña (*dead-bug wiring*) introdujo inductancia parásita adicional ($L_{\text{p}} \approx 1\text{ nH/mm}$) y acoplamiento de ruido ($v_{\text{ruido}} = L \cdot \frac{\text{d}i}{\text{d}t}$) en los nodos analógicos de control. La **revisión v2.0** contempla la corrección de la huella en KiCad y el reajuste de los divisores potenciométricos de histéresis para ensayos a menor potencia en laboratorio.

---

## 5. Estructura del Repositorio

```text
├── memoria/          # Código fuente en LaTeX (plantilla IEEE/UC3M), bibliografía (.bib) y figuras
├── hardware/         # Esquemas eléctricos, diseño de PCB en KiCad y Lista de Materiales (BOM)
├── simulacion/       # Modelos conductuales y con parásitos en PSIM + scripts de postprocesado en MATLAB
└── README.md         # Documentación principal del proyecto
