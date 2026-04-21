// Hilfsfunktionen für WebAuthn-Registrierung und -Login im Browser

function _b64urlToArrayBuffer(base64url) {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray.buffer;
}

function _arrayBufferToBase64url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64 = btoa(binary);
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function _fetchJSON(url, options) {
  const resp = await fetch(url, options || {});
  const data = await resp.json();
  if (!resp.ok || data.success === false) {
    const msg = data.message || ('HTTP-Fehler ' + resp.status);
    throw new Error(msg);
  }
  return data;
}

window.WebAuthnHelper = {
  async registerWebAuthnCredential() {
    if (!window.PublicKeyCredential) {
      throw new Error('WebAuthn wird von diesem Browser nicht unterstützt.');
    }

    const optionsResp = await _fetchJSON('/webauthn/register/options', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });

    const publicKey = optionsResp.publicKey;

    // Bytes-Felder in ArrayBuffer konvertieren
    publicKey.challenge = _b64urlToArrayBuffer(publicKey.challenge);
    publicKey.user.id = _b64urlToArrayBuffer(publicKey.user.id);

    if (publicKey.excludeCredentials) {
      publicKey.excludeCredentials = publicKey.excludeCredentials.map((cred) => {
        return {
          type: cred.type,
          id: _b64urlToArrayBuffer(cred.id),
          transports: cred.transports,
        };
      });
    }

    const credential = await navigator.credentials.create({ publicKey });
    if (!credential) {
      throw new Error('Kein Credential erstellt.');
    }

    const attestationResponse = credential.response;

    const clientDataJSON = _arrayBufferToBase64url(attestationResponse.clientDataJSON);
    const attestationObject = _arrayBufferToBase64url(attestationResponse.attestationObject);

    const verifyPayload = {
      id: credential.id,
      rawId: _arrayBufferToBase64url(credential.rawId),
      type: credential.type,
      clientDataJSON: clientDataJSON,
      attestationObject: attestationObject,
      label: 'Biometrisches Gerät',
    };

    await _fetchJSON('/webauthn/register/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(verifyPayload),
    });

    return true;
  },

  async loginWithWebAuthn(personalnummer, extraOptions) {
    if (!window.PublicKeyCredential) {
      throw new Error('WebAuthn wird von diesem Browser nicht unterstützt.');
    }

    const options = extraOptions || {};
    const usernameless = !personalnummer;

    const optionsResp = await _fetchJSON('/webauthn/login/options', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(usernameless ? {} : { personalnummer: personalnummer }),
    });

    const publicKey = optionsResp.publicKey;
    publicKey.challenge = _b64urlToArrayBuffer(publicKey.challenge);

    if (publicKey.allowCredentials && publicKey.allowCredentials.length > 0) {
      publicKey.allowCredentials = publicKey.allowCredentials.map((cred) => {
        return {
          type: cred.type,
          id: _b64urlToArrayBuffer(cred.id),
          transports: cred.transports,
        };
      });
    } else {
      // Usernameless / Passkey: leere allowCredentials -> Browser zeigt alle discoverable Credentials fuer die Domain
      delete publicKey.allowCredentials;
    }

    const getOptions = { publicKey: publicKey };
    if (options.mediation) {
      getOptions.mediation = options.mediation;
    }
    if (options.signal) {
      getOptions.signal = options.signal;
    }

    const assertion = await navigator.credentials.get(getOptions);
    if (!assertion) {
      throw new Error('Keine Antwort vom Authentifikator erhalten.');
    }

    const authResponse = assertion.response;

    const payload = {
      id: assertion.id,
      rawId: _arrayBufferToBase64url(assertion.rawId),
      type: assertion.type,
      clientDataJSON: _arrayBufferToBase64url(authResponse.clientDataJSON),
      authenticatorData: _arrayBufferToBase64url(authResponse.authenticatorData),
      signature: _arrayBufferToBase64url(authResponse.signature),
      userHandle: authResponse.userHandle
        ? _arrayBufferToBase64url(authResponse.userHandle)
        : null,
    };

    const nextParam =
      (typeof window !== 'undefined' &&
        window.location &&
        new URLSearchParams(window.location.search).get('next')) ||
      null;
    if (nextParam) {
      payload.next = nextParam;
    }

    const verifyResp = await _fetchJSON('/webauthn/login/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    return verifyResp.redirect_url || '/';
  },

  async isConditionalMediationAvailable() {
    try {
      if (!window.PublicKeyCredential) return false;
      if (typeof PublicKeyCredential.isConditionalMediationAvailable !== 'function') return false;
      return await PublicKeyCredential.isConditionalMediationAvailable();
    } catch (e) {
      return false;
    }
  },
};


