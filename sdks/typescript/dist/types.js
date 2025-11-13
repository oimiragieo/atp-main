"use strict";
/**
 * ATP Router Protocol Types and Interfaces
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.ValidationError = exports.AuthenticationError = exports.ConnectionError = exports.ATPClientError = void 0;
class ATPClientError extends Error {
    constructor(message, code) {
        super(message);
        this.code = code;
        this.name = 'ATPClientError';
    }
}
exports.ATPClientError = ATPClientError;
class ConnectionError extends ATPClientError {
    constructor(message) {
        super(message);
        this.name = 'ConnectionError';
    }
}
exports.ConnectionError = ConnectionError;
class AuthenticationError extends ATPClientError {
    constructor(message) {
        super(message, 'AUTHENTICATION_FAILED');
        this.name = 'AuthenticationError';
    }
}
exports.AuthenticationError = AuthenticationError;
class ValidationError extends ATPClientError {
    constructor(message) {
        super(message, 'VALIDATION_ERROR');
        this.name = 'ValidationError';
    }
}
exports.ValidationError = ValidationError;
//# sourceMappingURL=types.js.map