// Logica del chat: solo hace fetch al endpoint de Django.
// La API key de Gemini nunca llega al navegador; todo pasa por el servidor.
(function () {
    "use strict";

    var box = document.getElementById("chat-box");
    var form = document.getElementById("chat-form");
    var input = document.getElementById("chat-input");
    var boton = document.getElementById("chat-enviar");
    var vacio = document.getElementById("chat-vacio");
    var sugerencias = document.querySelectorAll(".sugerencias button");

    // El endpoint sale de la URL actual: /chatbot/ -> /chatbot/api/mensaje/
    var endpoint = window.location.pathname.replace(/\/$/, "") + "/api/mensaje/";

    var csrf = "";
    var token = form.querySelector('input[name="csrfmiddlewaretoken"]');
    if (token) {
        csrf = token.value;
    }

    var enviando = false;

    function desplazar() {
        box.scrollTop = box.scrollHeight;
    }

    function agregar(texto, clase) {
        if (vacio) {
            vacio.remove();
        }
        var p = document.createElement("p");
        p.className = "msg-burbuja " + clase;
        p.textContent = texto;
        box.appendChild(p);
        desplazar();
    }

    function bloquear(estado) {
        enviando = estado;
        boton.disabled = estado;
        input.disabled = estado;
        boton.textContent = estado ? "Pensando..." : "Enviar";
    }

    function enviar(texto) {
        if (enviando) {
            return;
        }

        agregar(texto, "msg-user");
        var esperando = document.createElement("p");
        esperando.className = "msg-enviando";
        esperando.textContent = "Consultando...";
        box.appendChild(esperando);
        desplazar();
        bloquear(true);

        var datos = new FormData();
        datos.append("mensaje", texto);
        datos.append("csrfmiddlewaretoken", csrf);

        fetch(endpoint, {
            method: "POST",
            body: datos,
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (respuesta) {
                return respuesta.json().then(function (datos) {
                    return { ok: respuesta.ok, datos: datos };
                });
            })
            .then(function (resultado) {
                if (resultado.ok) {
                    agregar(resultado.datos.respuesta, "msg-bot");
                } else {
                    agregar(resultado.datos.error || "Ocurrio un error.", "msg-error");
                }
            })
            .catch(function () {
                agregar(
                    "No se pudo conectar con el servidor. Revisa que Django este corriendo.",
                    "msg-error"
                );
            })
            .then(function () {
                esperando.remove();
                bloquear(false);
                input.focus();
            });
    }

    form.addEventListener("submit", function (evento) {
        evento.preventDefault();
        var texto = input.value.trim();
        if (!texto) {
            return;
        }
        input.value = "";
        enviar(texto);
    });

    sugerencias.forEach(function (botonSugerencia) {
        botonSugerencia.addEventListener("click", function () {
            enviar(botonSugerencia.dataset.texto);
        });
    });
})();
