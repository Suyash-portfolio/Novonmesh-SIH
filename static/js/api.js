const API = {
    base: '',

    async get(path) {
        try {
            const res = await fetch(this.base + path);
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        } catch (e) {
            console.error(`API GET ${path} failed:`, e);
            throw e;
        }
    },

    async post(path, data) {
        try {
            const res = await fetch(this.base + path, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        } catch (e) {
            console.error(`API POST ${path} failed:`, e);
            throw e;
        }
    },

    async put(path, data) {
        try {
            const res = await fetch(this.base + path, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: data ? JSON.stringify(data) : undefined,
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        } catch (e) {
            console.error(`API PUT ${path} failed:`, e);
            throw e;
        }
    },

    async del(path) {
        try {
            const res = await fetch(this.base + path, { method: 'DELETE' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        } catch (e) {
            console.error(`API DELETE ${path} failed:`, e);
            throw e;
        }
    },

    async upload(path, formData) {
        try {
            const res = await fetch(this.base + path, {
                method: 'POST',
                body: formData,
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ error: res.statusText }));
                throw new Error(err.error || res.statusText);
            }
            return res.json();
        } catch (e) {
            console.error(`API UPLOAD ${path} failed:`, e);
            throw e;
        }
    }
};
