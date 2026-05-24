(function () {
    const SKIN_INDEX = {
        classic: 0,
        nordic_wood: 1,
        blue_circuit: 2,
        royal_onyx: 3,
        nebula_crystal: 4,
    };
    const DEFAULT_SKIN = 'classic';
    const cache = new Map();
    let rendererState = null;

    function normalizeSkin(skinId) {
        return Object.prototype.hasOwnProperty.call(SKIN_INDEX, skinId) ? skinId : DEFAULT_SKIN;
    }

    function makePieceMesh(segments = 96) {
        const rings = [
            [-0.46, 0.60],
            [-0.38, 0.84],
            [-0.22, 0.99],
            [0.07, 1.0],
            [0.31, 0.9],
            [0.42, 0.68],
        ];
        const positions = [];
        const normals = [];
        const indices = [];

        const pushVertex = (x, y, z, nx, ny, nz) => {
            positions.push(x, y, z);
            normals.push(nx, ny, nz);
            return positions.length / 3 - 1;
        };

        for (let r = 0; r < rings.length; r++) {
            const prev = rings[Math.max(0, r - 1)];
            const next = rings[Math.min(rings.length - 1, r + 1)];
            const dy = next[0] - prev[0] || 1;
            const dr = next[1] - prev[1];
            const ny = -dr;
            const radial = Math.abs(dy);
            const normalLength = Math.hypot(radial, ny) || 1;
            for (let i = 0; i <= segments; i++) {
                const angle = (Math.PI * 2 * i) / segments;
                const x = Math.cos(angle);
                const z = Math.sin(angle);
                pushVertex(
                    x * rings[r][1],
                    rings[r][0],
                    z * rings[r][1],
                    (x * radial) / normalLength,
                    ny / normalLength,
                    (z * radial) / normalLength,
                );
            }
        }

        const stride = segments + 1;
        for (let r = 0; r < rings.length - 1; r++) {
            for (let i = 0; i < segments; i++) {
                const a = r * stride + i;
                const b = a + 1;
                const c = (r + 1) * stride + i;
                const d = c + 1;
                indices.push(a, c, b, b, c, d);
            }
        }

        const topCenter = pushVertex(0, rings[rings.length - 1][0] + 0.008, 0, 0, 1, 0);
        const topRingStart = positions.length / 3;
        const topY = rings[rings.length - 1][0] + 0.008;
        const topRadius = rings[rings.length - 1][1];
        for (let i = 0; i <= segments; i++) {
            const angle = (Math.PI * 2 * i) / segments;
            pushVertex(Math.cos(angle) * topRadius, topY, Math.sin(angle) * topRadius, 0, 1, 0);
        }
        for (let i = 0; i < segments; i++) {
            indices.push(topCenter, topRingStart + i, topRingStart + i + 1);
        }

        const bottomCenter = pushVertex(0, rings[0][0] - 0.008, 0, 0, -1, 0);
        const bottomRingStart = positions.length / 3;
        const bottomY = rings[0][0] - 0.008;
        const bottomRadius = rings[0][1];
        for (let i = 0; i <= segments; i++) {
            const angle = (Math.PI * 2 * i) / segments;
            pushVertex(Math.cos(angle) * bottomRadius, bottomY, Math.sin(angle) * bottomRadius, 0, -1, 0);
        }
        for (let i = 0; i < segments; i++) {
            indices.push(bottomCenter, bottomRingStart + i + 1, bottomRingStart + i);
        }

        return {
            positions: new Float32Array(positions),
            normals: new Float32Array(normals),
            indices: new Uint16Array(indices),
        };
    }

    function compileShader(gl, type, source) {
        const shader = gl.createShader(type);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            throw new Error(gl.getShaderInfoLog(shader) || 'Shader compile failed');
        }
        return shader;
    }

    function createProgram(gl) {
        const vertexSource = `
            attribute vec3 aPosition;
            attribute vec3 aNormal;
            uniform mat4 uMvp;
            uniform mat4 uModel;
            varying vec3 vNormal;
            varying vec3 vLocal;
            varying vec3 vWorld;

            void main() {
                vec4 world = uModel * vec4(aPosition, 1.0);
                vWorld = world.xyz;
                vLocal = aPosition;
                vNormal = normalize((uModel * vec4(aNormal, 0.0)).xyz);
                gl_Position = uMvp * vec4(aPosition, 1.0);
            }
        `;
        const fragmentSource = `
            precision mediump float;
            varying vec3 vNormal;
            varying vec3 vLocal;
            varying vec3 vWorld;
            uniform float uSkin;
            uniform float uSide;
            uniform float uKing;

            float hash(vec2 p) {
                return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
            }

            float noise(vec2 p) {
                vec2 i = floor(p);
                vec2 f = fract(p);
                vec2 u = f * f * (3.0 - 2.0 * f);
                return mix(
                    mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
                    mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x),
                    u.y
                );
            }

            vec3 gold() {
                return vec3(1.0, 0.72, 0.22);
            }

            void main() {
                vec3 n = normalize(vNormal);
                vec3 lightA = normalize(vec3(-0.45, 0.9, 0.55));
                vec3 lightB = normalize(vec3(0.6, 0.35, -0.55));
                vec3 eye = normalize(vec3(0.0, 1.9, 3.25) - vWorld);
                float diff = max(dot(n, lightA), 0.0) * 0.96 + max(dot(n, lightB), 0.0) * 0.34;
                float rimLight = pow(1.0 - max(dot(n, eye), 0.0), 2.0);
                float rr = length(vLocal.xz);
                float top = smoothstep(0.10, 0.26, vLocal.y);
                float edge = smoothstep(0.62, 0.9, rr);
                float sideBand = smoothstep(0.80, 0.96, rr) * (1.0 - smoothstep(0.23, 0.38, abs(vLocal.y)));
                float lowerSide = smoothstep(-0.36, -0.12, -vLocal.y) * smoothstep(0.62, 0.94, rr);
                float ang = atan(vLocal.z, vLocal.x);
                float grain = noise(vLocal.xz * 7.0 + vec2(vLocal.y * 3.0, 0.0));
                float line = sin((vLocal.x * 8.0 + vLocal.z * 10.0 + grain * 2.4));
                vec3 base;
                float specPower = 28.0;
                float specStrength = 0.28;
                float metalMask = 0.0;
                float glow = 0.0;

                if (uSkin < 0.5) {
                    if (uSide < 0.5) {
                        base = mix(vec3(0.98, 0.96, 0.89), vec3(0.72, 0.69, 0.61), edge * 0.35 + grain * 0.08);
                    } else {
                        base = mix(vec3(0.025, 0.028, 0.034), vec3(0.23, 0.24, 0.27), top * 0.28 + grain * 0.08);
                    }
                    specPower = 36.0;
                    specStrength = 0.32;
                } else if (uSkin < 1.5) {
                    float rings = 0.5 + 0.5 * sin(rr * 28.0 + grain * 5.0 + vLocal.y * 12.0);
                    if (uSide < 0.5) {
                        base = mix(vec3(0.78, 0.54, 0.28), vec3(0.97, 0.79, 0.45), rings * 0.42 + top * 0.18);
                    } else {
                        base = mix(vec3(0.14, 0.075, 0.04), vec3(0.42, 0.22, 0.09), rings * 0.46 + top * 0.12);
                    }
                    base *= 1.0 - edge * 0.16;
                    base *= 1.0 - lowerSide * 0.20;
                    specPower = 22.0;
                    specStrength = 0.22;
                } else if (uSkin < 2.5) {
                    vec3 accent = vec3(0.08, 0.78, 1.0);
                    if (uSide < 0.5) {
                        base = mix(vec3(0.94, 0.97, 1.0), vec3(0.60, 0.72, 0.84), edge * 0.32 + grain * 0.06);
                    } else {
                        base = mix(vec3(0.035, 0.045, 0.065), vec3(0.12, 0.18, 0.28), top * 0.32 + grain * 0.08);
                    }
                    float circuit = smoothstep(0.955, 1.0, sin(ang * 12.0 + rr * 18.0)) * top;
                    base = mix(base, accent, max(sideBand * 0.70, circuit * 0.42));
                    glow = max(sideBand, circuit) * 0.28;
                    specPower = 46.0;
                    specStrength = 0.4;
                } else if (uSkin < 3.5) {
                    float vein = smoothstep(0.72, 0.98, abs(line)) * (0.55 + grain * 0.45);
                    if (uSide < 0.5) {
                        base = mix(vec3(0.94, 0.91, 0.84), vec3(0.40, 0.43, 0.50), vein * 0.42);
                    } else {
                        base = mix(vec3(0.015, 0.018, 0.022), vec3(0.13, 0.10, 0.16), vein * 0.55 + top * 0.12);
                    }
                    metalMask = max(sideBand, top * smoothstep(0.48, 0.82, rr));
                    base = mix(base, gold(), metalMask * 0.72);
                    specPower = 74.0;
                    specStrength = 0.62;
                } else {
                    float star = step(0.986, hash(floor((vLocal.xz + grain) * 22.0)));
                    vec3 blue = vec3(0.07, 0.28, 0.95);
                    vec3 violet = vec3(0.75, 0.18, 0.92);
                    vec3 cyan = vec3(0.08, 0.95, 1.0);
                    vec3 darkCrystal = uSide < 0.5 ? vec3(0.48, 0.78, 1.0) : vec3(0.06, 0.04, 0.18);
                    base = mix(darkCrystal, mix(blue, violet, 0.5 + 0.5 * sin(ang * 2.0 + rr * 4.5)), 0.52 + grain * 0.26);
                    base += cyan * star * top * 0.55;
                    base = mix(base, cyan, sideBand * 0.72);
                    glow = sideBand * 0.55 + star * top * 0.38;
                    specPower = 96.0;
                    specStrength = 0.78;
                }

                float crownCore = smoothstep(0.04, 0.14, rr) * (1.0 - smoothstep(0.56, 0.66, rr));
                float crownRing = smoothstep(0.42, 0.50, rr) * (1.0 - smoothstep(0.62, 0.70, rr));
                float crownTeeth = smoothstep(0.16, 0.56, rr) * (1.0 - smoothstep(0.57, 0.66, rr));
                crownTeeth *= smoothstep(0.08, 0.96, 0.5 + 0.5 * sin(ang * 5.0));
                float crown = uKing * top * max(max(crownCore * 0.95, crownRing * 0.9), crownTeeth * 0.62);
                vec3 crownColor = uSkin > 2.5 ? gold() : vec3(1.0, 0.84, 0.18);
                base = mix(base, crownColor, crown);
                metalMask = max(metalMask, crown);

                vec3 halfVec = normalize(lightA + eye);
                float spec = pow(max(dot(n, halfVec), 0.0), specPower) * specStrength;
                vec3 lit = base * (0.30 + diff) + vec3(spec) * (0.55 + metalMask * 0.9);
                lit += base * rimLight * (0.36 + metalMask * 0.48);
                lit += vec3(0.08, 0.85, 1.0) * glow;
                lit *= 1.0 - lowerSide * 0.22;
                lit = mix(lit, vec3(0.0), smoothstep(0.95, 1.12, rr) * 0.12);

                gl_FragColor = vec4(lit, 1.0);
            }
        `;
        const program = gl.createProgram();
        gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, vertexSource));
        gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, fragmentSource));
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
            throw new Error(gl.getProgramInfoLog(program) || 'Program link failed');
        }
        return program;
    }

    function mat4Multiply(a, b) {
        const out = new Float32Array(16);
        for (let col = 0; col < 4; col++) {
            for (let row = 0; row < 4; row++) {
                out[col * 4 + row] =
                    a[0 * 4 + row] * b[col * 4 + 0] +
                    a[1 * 4 + row] * b[col * 4 + 1] +
                    a[2 * 4 + row] * b[col * 4 + 2] +
                    a[3 * 4 + row] * b[col * 4 + 3];
            }
        }
        return out;
    }

    function mat4Ortho(left, right, bottom, top, near, far) {
        const out = new Float32Array(16);
        out[0] = 2 / (right - left);
        out[5] = 2 / (top - bottom);
        out[10] = -2 / (far - near);
        out[12] = -(right + left) / (right - left);
        out[13] = -(top + bottom) / (top - bottom);
        out[14] = -(far + near) / (far - near);
        out[15] = 1;
        return out;
    }

    function vec3Normalize(v) {
        const length = Math.hypot(v[0], v[1], v[2]) || 1;
        return [v[0] / length, v[1] / length, v[2] / length];
    }

    function vec3Cross(a, b) {
        return [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        ];
    }

    function vec3Dot(a, b) {
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    }

    function mat4LookAt(eye, center, up) {
        const z = vec3Normalize([eye[0] - center[0], eye[1] - center[1], eye[2] - center[2]]);
        const x = vec3Normalize(vec3Cross(up, z));
        const y = vec3Cross(z, x);
        const out = new Float32Array(16);
        out[0] = x[0];
        out[1] = y[0];
        out[2] = z[0];
        out[4] = x[1];
        out[5] = y[1];
        out[6] = z[1];
        out[8] = x[2];
        out[9] = y[2];
        out[10] = z[2];
        out[12] = -vec3Dot(x, eye);
        out[13] = -vec3Dot(y, eye);
        out[14] = -vec3Dot(z, eye);
        out[15] = 1;
        return out;
    }

    function mat4RotateY(angle) {
        const out = new Float32Array(16);
        const c = Math.cos(angle);
        const s = Math.sin(angle);
        out[0] = c;
        out[2] = -s;
        out[5] = 1;
        out[8] = s;
        out[10] = c;
        out[15] = 1;
        return out;
    }

    function drawKingCrownOverlay(sourceCanvas, size) {
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        if (!ctx) return sourceCanvas;
        ctx.drawImage(sourceCanvas, 0, 0, size, size);
        const cx = size * 0.5;
        const cy = size * 0.33;
        const w = size * 0.34;
        const h = size * 0.19;
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(0);
        ctx.shadowColor = 'rgba(0, 0, 0, 0.36)';
        ctx.shadowBlur = size * 0.025;
        ctx.shadowOffsetY = size * 0.018;
        ctx.strokeStyle = 'rgba(255, 213, 76, 0.62)';
        ctx.lineWidth = Math.max(1.6, size * 0.016);
        ctx.beginPath();
        ctx.ellipse(0, h * 0.26, w * 0.54, h * 0.28, 0.02, 0, Math.PI * 2);
        ctx.stroke();
        const gradient = ctx.createLinearGradient(-w * 0.5, -h * 0.5, w * 0.5, h * 0.62);
        gradient.addColorStop(0, '#fff2a8');
        gradient.addColorStop(0.48, '#f7bf35');
        gradient.addColorStop(1, '#b7770d');
        ctx.fillStyle = gradient;
        ctx.strokeStyle = 'rgba(72, 44, 4, 0.78)';
        ctx.lineWidth = Math.max(1.8, size * 0.018);
        ctx.beginPath();
        ctx.moveTo(-w * 0.48, h * 0.22);
        ctx.lineTo(-w * 0.38, -h * 0.20);
        ctx.lineTo(-w * 0.16, h * 0.02);
        ctx.lineTo(0, -h * 0.36);
        ctx.lineTo(w * 0.16, h * 0.02);
        ctx.lineTo(w * 0.38, -h * 0.20);
        ctx.lineTo(w * 0.48, h * 0.22);
        ctx.quadraticCurveTo(0, h * 0.46, -w * 0.48, h * 0.22);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.strokeStyle = 'rgba(255,255,255,0.82)';
        ctx.lineWidth = Math.max(1, size * 0.007);
        ctx.stroke();
        ctx.fillStyle = 'rgba(255,255,255,0.82)';
        [-0.38, 0, 0.38].forEach(point => {
            ctx.beginPath();
            ctx.arc(w * point, -h * (point === 0 ? 0.36 : 0.20), size * 0.018, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.restore();
        return canvas;
    }

    function initRenderer() {
        if (rendererState) return rendererState;
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl', {
            alpha: true,
            antialias: true,
            premultipliedAlpha: false,
            preserveDrawingBuffer: true,
        });
        if (!gl) {
            rendererState = { gl: null };
            return rendererState;
        }

        try {
            const program = createProgram(gl);
            const mesh = makePieceMesh();
            const positionBuffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
            gl.bufferData(gl.ARRAY_BUFFER, mesh.positions, gl.STATIC_DRAW);
            const normalBuffer = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
            gl.bufferData(gl.ARRAY_BUFFER, mesh.normals, gl.STATIC_DRAW);
            const indexBuffer = gl.createBuffer();
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
            rendererState = {
                canvas,
                gl,
                program,
                mesh,
                positionBuffer,
                normalBuffer,
                indexBuffer,
                locations: {
                    position: gl.getAttribLocation(program, 'aPosition'),
                    normal: gl.getAttribLocation(program, 'aNormal'),
                    mvp: gl.getUniformLocation(program, 'uMvp'),
                    model: gl.getUniformLocation(program, 'uModel'),
                    skin: gl.getUniformLocation(program, 'uSkin'),
                    side: gl.getUniformLocation(program, 'uSide'),
                    king: gl.getUniformLocation(program, 'uKing'),
                },
            };
        } catch (error) {
            console.warn('3D checker renderer failed:', error);
            rendererState = { gl: null };
        }
        return rendererState;
    }

    function renderDataUrl(options) {
        const skinId = normalizeSkin(options.skinId);
        const color = options.color === 'black' ? 'black' : 'white';
        const king = options.king ? 1 : 0;
        const size = Math.max(96, Number(options.size) || 192);
        const key = `${skinId}|${color}|${king}|${size}`;
        if (cache.has(key)) return cache.get(key);

        const state = initRenderer();
        if (!state.gl) return null;

        const { canvas, gl, program, mesh, positionBuffer, normalBuffer, indexBuffer, locations } = state;
        canvas.width = size;
        canvas.height = size;
        gl.viewport(0, 0, size, size);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
        gl.enable(gl.DEPTH_TEST);
        gl.disable(gl.CULL_FACE);
        gl.useProgram(program);

        gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
        gl.enableVertexAttribArray(locations.position);
        gl.vertexAttribPointer(locations.position, 3, gl.FLOAT, false, 0, 0);

        gl.bindBuffer(gl.ARRAY_BUFFER, normalBuffer);
        gl.enableVertexAttribArray(locations.normal);
        gl.vertexAttribPointer(locations.normal, 3, gl.FLOAT, false, 0, 0);

        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, indexBuffer);

        const model = mat4RotateY(color === 'white' ? -0.42 : 0.52);
        const view = mat4LookAt([0, 2.08, 3.05], [0, 0.02, 0], [0, 1, 0]);
        const projection = mat4Ortho(-1.06, 1.06, -1.06, 1.06, 0.1, 8);
        const mvp = mat4Multiply(projection, mat4Multiply(view, model));

        gl.uniformMatrix4fv(locations.mvp, false, mvp);
        gl.uniformMatrix4fv(locations.model, false, model);
        gl.uniform1f(locations.skin, SKIN_INDEX[skinId]);
        gl.uniform1f(locations.side, color === 'black' ? 1 : 0);
        gl.uniform1f(locations.king, king);
        gl.drawElements(gl.TRIANGLES, mesh.indices.length, gl.UNSIGNED_SHORT, 0);

        const outputCanvas = king ? drawKingCrownOverlay(canvas, size) : canvas;
        const url = outputCanvas.toDataURL('image/png');
        cache.set(key, url);
        return url;
    }

    function enhancePiece(element, options) {
        if (!element) return;
        const url = renderDataUrl({
            skinId: options.skinId,
            color: options.color,
            king: options.king,
            size: 256,
        });
        if (!url) return;
        const img = document.createElement('img');
        img.className = 'checker-3d-img';
        img.alt = '';
        img.draggable = false;
        img.src = url;
        element.replaceChildren(img);
        element.classList.add('has-3d');
        element.dataset.skin = normalizeSkin(options.skinId);
    }

    function renderPreview(target, options = {}) {
        const size = Math.max(160, Number(options.size) || 320);
        const url = renderDataUrl({
            skinId: options.skinId,
            color: options.color,
            king: options.king,
            size,
        });
        if (!url || !target) return;

        if (target instanceof HTMLImageElement) {
            target.src = url;
            target.alt = '';
            return;
        }

        if (target instanceof HTMLCanvasElement) {
            const rect = target.getBoundingClientRect();
            const dpr = Math.min(2, window.devicePixelRatio || 1);
            const width = Math.max(1, Math.round((rect.width || 160) * dpr));
            const height = Math.max(1, Math.round((rect.height || 160) * dpr));
            target.width = width;
            target.height = height;
            const ctx = target.getContext('2d');
            if (!ctx) return;
            const image = new Image();
            image.onload = () => {
                ctx.clearRect(0, 0, width, height);
                const drawSize = Math.min(width, height);
                ctx.drawImage(image, (width - drawSize) / 2, (height - drawSize) / 2, drawSize, drawSize);
            };
            image.src = url;
        }
    }

    window.Checker3D = {
        enhancePiece,
        renderDataUrl,
        renderPreview,
        normalizeSkin,
    };
})();
