(function(global) {
    "use strict";

    var CONTROL_TYPES = {
        hello: true,
        heartbeat: true,
        pong: true
    };

    function getWebSocketPort(fallbackPort) {
        var params = new URLSearchParams(global.location.search);
        if (params.has("port")) {
            return parseInt(params.get("port"), 10) || fallbackPort || 8767;
        }
        var cssPort = getComputedStyle(document.documentElement)
            .getPropertyValue("--websocket-port")
            .trim();
        return parseInt(cssPort, 10) || fallbackPort || 8767;
    }

    function getWebSocketHost() {
        var params = new URLSearchParams(global.location.search);
        if (params.has("host")) return params.get("host");
        return "localhost";
    }

    function normalizeTypes(options) {
        var types = options.types || options.type || [];
        if (typeof types === "string") types = [types];
        var out = {};
        types.forEach(function(type) { out[type] = true; });
        return out;
    }

    function connect(options) {
        options = options || {};

        var types = normalizeTypes(options);
        var target = options.target || options.type || "";
        var reconnectDelay = options.reconnectDelay || 3000;
        var healthIntervalMs = options.healthIntervalMs || 5000;
        var staleTimeoutMs = options.staleTimeoutMs || 18000;
        var socket = null;
        var reconnectTimer = null;
        var healthTimer = null;
        var lastSeen = 0;
        var manualClose = false;

        function notifyState(state) {
            if (typeof options.onState === "function") options.onState(state);
        }

        function clearReconnectTimer() {
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
        }

        function clearHealthTimer() {
            if (healthTimer) {
                clearInterval(healthTimer);
                healthTimer = null;
            }
        }

        function send(data) {
            if (!socket || socket.readyState !== WebSocket.OPEN) return false;
            try {
                socket.send(JSON.stringify(data));
                return true;
            } catch (e) {
                return false;
            }
        }

        function requestLatest() {
            if (!target) return;
            send({type: "request_latest", target: target});
        }

        function closeStaleSocket() {
            if (!socket) return;
            try {
                socket.close();
            } catch (e) {}
        }

        function startHealthTimer() {
            clearHealthTimer();
            healthTimer = setInterval(function() {
                if (!socket || socket.readyState !== WebSocket.OPEN) return;
                if (Date.now() - lastSeen > staleTimeoutMs) {
                    closeStaleSocket();
                    return;
                }
                send({type: "ping", time: Date.now()});
                requestLatest();
            }, healthIntervalMs);
        }

        function scheduleReconnect() {
            if (manualClose || reconnectTimer) return;
            notifyState("disconnected");
            reconnectTimer = setTimeout(function() {
                reconnectTimer = null;
                open();
            }, reconnectDelay);
        }

        function open() {
            if (socket && (
                socket.readyState === WebSocket.OPEN ||
                socket.readyState === WebSocket.CONNECTING
            )) {
                return;
            }

            clearReconnectTimer();
            clearHealthTimer();
            manualClose = false;
            lastSeen = Date.now();

            var port = getWebSocketPort(options.fallbackPort || 8767);
            var host = getWebSocketHost();
            socket = new WebSocket("ws://" + host + ":" + port);
            notifyState("connecting");

            socket.onopen = function() {
                lastSeen = Date.now();
                notifyState("connected");
                requestLatest();
                startHealthTimer();
            };

            socket.onmessage = function(event) {
                var message;
                lastSeen = Date.now();
                try {
                    message = JSON.parse(event.data);
                } catch (e) {
                    return;
                }

                if (CONTROL_TYPES[message.type]) return;
                if (!types[message.type]) return;
                if (typeof options.onData === "function") {
                    options.onData(message.data, message);
                }
            };

            socket.onerror = function() {
                closeStaleSocket();
            };

            socket.onclose = function() {
                clearHealthTimer();
                scheduleReconnect();
            };
        }

        function close() {
            manualClose = true;
            clearReconnectTimer();
            clearHealthTimer();
            if (socket) closeStaleSocket();
        }

        global.addEventListener("pageshow", function() {
            if (!socket || socket.readyState === WebSocket.CLOSED) open();
        });
        global.addEventListener("online", open);
        global.addEventListener("beforeunload", close);

        open();
        return {
            close: close,
            reconnect: function() {
                close();
                manualClose = false;
                socket = null;
                open();
            },
            requestLatest: requestLatest
        };
    }

    global.SDVXWebSocketClient = {
        connect: connect,
        getWebSocketPort: getWebSocketPort
    };
})(window);
