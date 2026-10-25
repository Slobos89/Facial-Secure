/**
 * SecuGen Hamster Plus Client (Modo Nativo FDx SDK Pro 100% Gratuito)
 * Integración biométrica para facIAL Secure
 */

/**
 * Traduce códigos de error de SecuGen a mensajes claros en español
 */
function secugenErrorMessage(errorCode, defaultMsg) {
    const errorMap = {
        0: 'Operación exitosa',
        1: 'Error en tiempo de creación',
        2: 'Función no soportada',
        3: 'Parámetro inválido',
        51: 'Lector SecuGen no detectado. Verifique que el cable USB esté conectado.',
        52: 'Fallo al cargar el driver del lector SecuGen.',
        53: 'Fallo de comunicación con el driver.',
        54: 'Tiempo de espera agotado. No se colocó el dedo en el sensor a tiempo.',
        55: 'Lector SecuGen Hamster Plus no detectado. Conecte el cable USB.',
        101: 'Memoria insuficiente.',
        105: 'Calidad de huella insuficiente. Limpie el sensor y presione con firmeza.',
        1000: 'Calidad de huella insuficiente. Limpie el sensor y presione con firmeza.'
    };
    return errorMap[errorCode] || defaultMsg || `Error SecuGen código: ${errorCode}`;
}

/**
 * Captura la huella dactilar directamente a través del driver nativo de Django / FDx SDK Pro
 */
async function secugenCapture(options = {}) {
    const timeout = options.timeout || 10000;
    const quality = options.quality || 40;

    // 1. Intentar captura nativa directa con el servidor Django (FDx SDK Pro 64-bit)
    try {
        const url = `/usuarios/api/capturar-huella-sensor/?timeout=${timeout}&quality=${quality}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout + 4000);

        const response = await fetch(url, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                return {
                    success: true,
                    template: data.template,
                    bmpBase64: data.imagen_base64,
                    quality: data.calidad || 0,
                    width: data.width || 260,
                    height: data.height || 300,
                    errorCode: 0,
                    message: data.mensaje || 'Huella capturada correctamente con SecuGen'
                };
            }
            // Si el servidor está en la nube (Render) no tendrá el sensor USB conectado; intentar fallback local
            console.warn('Servidor sin sensor USB local o driver disponible:', data.error);
        }
    } catch (err) {
        console.warn("Fallo endpoint nativo Django, probando WebAPI fallback:", err);
    }

    // 2. Fallback secundario a SecuGen WebAPI si estuviera activo
    try {
        const webApiParams = new URLSearchParams({
            Timeout: timeout,
            Quality: quality,
            templateFormat: 'ANSI378',
            imageWSQRate: '0.75'
        });

        const resp = await fetch('https://localhost:8443/SGIFPCapture', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: webApiParams.toString()
        });

        if (resp.ok) {
            const data = await resp.json();
            if (data.ErrorCode === 0) {
                return {
                    success: true,
                    template: data.TemplateBase64,
                    bmpBase64: data.BMPBase64,
                    quality: data.ImageQuality || 0,
                    errorCode: 0,
                    message: 'Huella capturada correctamente'
                };
            }
        }
    } catch (e) {
        // Fallback no disponible
    }

    const isCloud = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
    const msg = isCloud 
        ? 'Lector SecuGen USB no accesible en la nube (Render). El sensor físico está conectado a tu computador local. Para validar con huella ejecuta el sistema en local (http://127.0.0.1:8000) o activa SecuGen WebAPI.'
        : 'No se pudo comunicar con el lector SecuGen Hamster Plus. Asegúrese de que el cable USB esté conectado y los drivers instalados.';

    return {
        success: false,
        errorCode: 55,
        error: msg
    };
}

/**
 * Verifica si el sensor SecuGen está conectado
 */
async function secugenCheckService() {
    try {
        const res = await fetch('/usuarios/api/estado-sensor/');
        if (res.ok) {
            const data = await res.json();
            return data.conectado;
        }
    } catch (e) {}
    return false;
}
