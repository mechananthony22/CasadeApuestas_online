# ADR 0002: Estrategia de Validación KYC — Verificación Offline vs. Integración RENIEC

* **ID:** 0002
* **Título:** Estrategia de Validación KYC (Conoce a Tu Cliente)
* **Fecha:** 2026-05-26
* **Autor:** Grupo de Desarrollo - FairBet Lab
* **Estado:** Decisión Tomada

---

## Contexto

La Ley 31557 y su reglamento DS 005-2023-MINCETUR exigen que toda plataforma de apuestas deportivas verifique la identidad de sus usuarios, incluyendo mayoría de edad y validez del DNI peruano, antes de permitirles operar con moneda virtual.

Existen dos estrategias principales para realizar esta verificación:
1. **Offline / Algoritmo Local**: Validar el formato y el dígito verificador del DNI usando el algoritmo de Módulo-11 sin conexión a servicios externos.
2. **Online / RENIEC**: Conectarse en tiempo real a la API oficial de RENIEC para confirmar que el DNI corresponde al nombre, apellido y fecha de nacimiento registrados.

La decisión sobre cuál estrategia adoptar tiene implicaciones directas sobre la complejidad técnica, el costo de mantenimiento, la privacidad del usuario y el nivel de cumplimiento regulatorio alcanzado.

---

## Opciones Consideradas

### Opción 1: Verificación Offline mediante Algoritmo Módulo-11 (Elegida)
Implementar localmente el algoritmo matemático oficial del DNI peruano para validar el dígito verificador del documento sin depender de ningún servicio externo.

**Cómo funciona el algoritmo Módulo-11:**
1. Se toman los primeros 7 dígitos del DNI.
2. Cada dígito se multiplica por un peso del vector oficial: `[3, 2, 7, 6, 5, 4, 3, 2]`.
3. Se suman todos los productos.
4. Se calcula el residuo de dividir la suma entre 11.
5. El residuo se convierte en el carácter verificador esperado.
6. Se compara con el 8vo dígito del DNI ingresado por el usuario.

* **Pros:**
  * Cero dependencia de servicios externos. No hay riesgo de fallos por API de terceros.
  * Respuesta instantánea (microsegundos) sin latencia de red.
  * Sin costo adicional de licenciamiento de API o cuota por consulta.
  * No se envían datos personales a servicios externos (mejor privacidad).
  * Implementación sencilla, auditable y testeable con property-based testing.
* **Contras:**
  * No confirma que el DNI esté activo o asignado a una persona real.
  * Un usuario podría fabricar un DNI matemáticamente válido pero ficticio.
  * El nivel de cumplimiento regulatorio es "KYC simulado", no KYC completo.

### Opción 2: Integración con API de RENIEC (Online / Tiempo Real)
Conectarse al servicio web de RENIEC o a un proveedor de verificación de identidad (Apilayer, APIs.pe, etc.) para confirmar en tiempo real que el DNI, nombre y fecha de nacimiento coinciden con los registros de RENIEC.

* **Pros:**
  * Verificación real de identidad contra la base de datos oficial del Estado peruano.
  * Cumplimiento regulatorio completo para entornos de producción real.
  * Imposible registrarse con un DNI fabricado.
* **Contras:**
  * Requiere contrato con un proveedor o acuerdo con RENIEC (costo económico).
  * Latencia adicional de 500ms-2000ms por petición de registro.
  * Dependencia de la disponibilidad del servicio externo (RENIEC tiene incidencias frecuentes).
  * La API de RENIEC no es de acceso público y tiene requisitos legales de uso.
  * Complejidad adicional: manejo de timeouts, reintentos, circuit breakers.

---

## Decisión
Hemos elegido la **Opción 1 (Verificación Offline - Módulo-11)** para esta implementación educativa.

**Justificación:**
Este proyecto es explícitamente una **plataforma educativa con moneda virtual** que no maneja dinero real. El requerimiento del reto establece `"Registro y KYC (Conoce tu cliente) simulado"`, lo que confirma que la verificación no necesita ser integración real con RENIEC. La verificación offline garantiza que el sistema sea autónomo, auditable en tests automáticos, sin costos de API y sin fugas de datos personales a terceros.

---

## Consecuencias

* **Lo que se vuelve más fácil:**
  * El proceso de registro es instantáneo (respuesta en < 100ms).
  * Los tests automatizados pueden correr sin mocks de APIs externas.
  * La plataforma no tiene dependencias de servicios externos en su núcleo.
* **Lo que se vuelve más difícil:**
  * Un atacante podría calcular DNIs matemáticamente válidos pero ficticios para registrarse.
  * El nivel de KYC no sería suficiente para una operación regulada real.
* **Deuda técnica asumida:**
  * Si el proyecto evolucionara a producción real, se debería implementar la Opción 2 e integrar un proveedor de verificación de identidad (ej: Apilayer RENIEC, Veriff, Jumio).
  * Se debe documentar claramente en `/docs/anti-ai-disclosure.md` y en el reporte de compliance que este KYC es simulado (Ley 31557 no cumplida en totalidad).

---

**Autocrítica regulatoria:** El diseño actual cubre el espíritu del Art. 8 de la Ley 31557 (verificación de identidad y mayoría de edad) pero NO cumple la letra completa de la norma, ya que no hay confirmación contra registros oficiales del Estado. Esto es aceptable en el contexto educativo del reto y se documenta honestamente.
