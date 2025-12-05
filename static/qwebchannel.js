(function(global) {
    "use strict";
    var QWebChannel = function(transport, initCallback) {
        if (typeof transport !== "object" || typeof transport.send !== "function") {
            console.error("The QWebChannel transport object is expected to have a send function.");
            return;
        }
        this.transport = transport;
        this.execCallbacks = {};
        this.execId = 0;
        this.objects = {};
        var channel = this;
        this.transport.onmessage = function(message) {
            var data = message.data;
            if (typeof data === "string") {
                data = JSON.parse(data);
            }
            switch (data.type) {
            case QWebChannel.Signal:
                channel.handleSignal(data);
                break;
            case QWebChannel.Response:
                channel.handleResponse(data);
                break;
            case QWebChannel.PropertyUpdate:
                channel.handlePropertyUpdate(data);
                break;
            default:
                console.error("invalid message received:", message.data);
                break;
            }
        };
        this.send({
            type: QWebChannel.Init
        }, function(response) {
            for (var objectName in response) {
                var object = new QObject(objectName, response[objectName], channel);
                channel.objects[objectName] = object;
                Object.defineProperty(global, objectName, {
                    value: object,
                    configurable: true
                });
            }
            if (initCallback) {
                initCallback(channel);
            }
        });
    };
    QWebChannel.prototype.send = function(data, callback) {
        if (typeof callback !== "function") {
            console.error("Cannot send message without callback function. Message is:", JSON.stringify(data));
            return;
        }
        var execId = this.execId++;
        this.execCallbacks[execId] = callback;
        data.id = execId;
        this.transport.send(JSON.stringify(data));
    };
    QWebChannel.prototype.handleSignal = function(message) {
        var object = this.objects[message.object];
        if (object) {
            object.signalEmitted(message.signal, message.args);
        }
    };
    QWebChannel.prototype.handleResponse = function(message) {
        var callback = this.execCallbacks[message.id];
        if (callback) {
            callback(message.data);
            delete this.execCallbacks[message.id];
        }
    };
    QWebChannel.prototype.handlePropertyUpdate = function(message) {
        for (var i in message.data) {
            var data = message.data[i];
            var object = this.objects[data.object];
            if (object) {
                object.propertyUpdate(data.signals, data.properties);
            }
        }
    };
    QWebChannel.Init = 1;
    QWebChannel.Signal = 2;
    QWebChannel.PropertyUpdate = 3;
    QWebChannel.InvokeMethod = 4;
    QWebChannel.ConnectToSignal = 5;
    QWebChannel.DisconnectFromSignal = 6;
    QWebChannel.SetProperty = 7;
    QWebChannel.Response = 8;
    var QObject = function(name, data, webChannel) {
        this.__id__ = name;
        this.webChannel = webChannel;
        this.__objectSignals__ = {};
        for (var i in data.methods) {
            var method = data.methods[i];
            this[method.name] = this.createMethod(method.name, method.paramNames, method.returnType);
        }
        for (var i in data.properties) {
            var property = data.properties[i];
            this.createProperty(property.name, property.type, property.notifySignal);
        }
        for (var i in data.signals) {
            var signal = data.signals[i];
            this.createSignal(signal.name, signal.paramNames);
        }
    };
    QObject.prototype.createMethod = function(name, paramNames, returnType) {
        var object = this;
        return function() {
            var args = [];
            for (var i = 0; i < arguments.length; i++) {
                args.push(arguments[i]);
            }
            var newArgs = [];
            for (var i = 0; i < paramNames.length; i++) {
                if (i < args.length) {
                    newArgs.push(args[i]);
                } else {
                    newArgs.push(undefined);
                }
            }
            var promise;
            var resolver;
            var rejector;
            if (returnType !== "") {
                promise = new Promise(function(resolve, reject) {
                    resolver = resolve;
                    rejector = reject;
                });
            }
            object.webChannel.send({
                type: QWebChannel.InvokeMethod,
                object: object.__id__,
                method: name,
                args: newArgs
            }, function(response) {
                if (response !== undefined) {
                    if (resolver) {
                        resolver(response);
                    }
                } else if (rejector) {
                    rejector();
                }
            });
            return promise;
        };
    };
    QObject.prototype.createProperty = function(name, type, notifySignal) {
        var object = this;
        var backingValue = undefined;
        Object.defineProperty(this, name, {
            get: function() {
                return backingValue;
            },
            set: function(value) {
                if (value === backingValue) return;
                backingValue = value;
                object.webChannel.send({
                    type: QWebChannel.SetProperty,
                    object: object.__id__,
                    property: name,
                    value: value
                }, function() {});
            }
        });
        if (notifySignal) {
            if (Array.isArray(notifySignal)) {
                notifySignal = notifySignal[0];
            }
            this[notifySignal].connect(function() {
                var args = [].slice.call(arguments);
                backingValue = args[0];
            });
        }
    };
    QObject.prototype.createSignal = function(name, paramNames) {
        var object = this;
        var signal = this[name] = {
            connect: function(callback) {
                if (typeof callback !== "function") {
                    console.error("Bad callback given to connect to signal " + name);
                    return;
                }
                var connections = object.__objectSignals__[name];
                if (!connections) {
                    connections = object.__objectSignals__[name] = [];
                    object.webChannel.send({
                        type: QWebChannel.ConnectToSignal,
                        object: object.__id__,
                        signal: name
                    }, function() {});
                }
                connections.push(callback);
            },
            disconnect: function(callback) {
                var connections = object.__objectSignals__[name];
                if (!connections) {
                    return;
                }
                var idx = connections.indexOf(callback);
                if (idx === -1) {
                    return;
                }
                connections.splice(idx, 1);
                if (connections.length === 0) {
                    object.webChannel.send({
                        type: QWebChannel.DisconnectFromSignal,
                        object: object.__id__,
                        signal: name
                    }, function() {});
                }
            }
        };
        signal.emitted = function() {
            var args = [].slice.call(arguments);
            var connections = object.__objectSignals__[name];
            if (connections) {
                connections.forEach(function(callback) {
                    callback.apply(callback, args);
                });
            }
        };
    };
    QObject.prototype.signalEmitted = function(signalName, args) {
        if (this[signalName] && this[signalName].emitted) {
            this[signalName].emitted.apply(this[signalName].emitted, args);
        }
    };
    QObject.prototype.propertyUpdate = function(signals, properties) {
        for (var i in properties) {
            var propertyName = i;
            var propertyValue = properties[i];
            this[propertyName] = propertyValue;
        }
        for (var i in signals) {
            var signalName = i;
            var signalArgs = signals[i];
            this.signalEmitted(signalName, signalArgs);
        }
    };
    global.QWebChannel = QWebChannel;
})(this);
