/**
 * Vercel Serverless Function — API 代理
 * 将所有 /api/proxy/<backend>/<path> 请求转发到对应的中国 AI 平台
 *
 * 部署后，前端与代理同域，彻底解决 CORS 问题。
 */

// 后端 API 地址映射
const BACKENDS = {
    dashscope:   'https://dashscope.aliyuncs.com',
    siliconflow: 'https://api.siliconflow.cn',
    zhipu:       'https://open.bigmodel.cn',
};

// 请求头黑名单（这些头由 fetch 自动管理，不能手动设置）
const FORBIDDEN_REQ_HEADERS = new Set([
    'host', 'connection', 'transfer-encoding',
    'content-length', 'expect',
]);

// 响应头黑名单（不转发回客户端）
const FORBIDDEN_RES_HEADERS = new Set([
    'transfer-encoding', 'connection', 'keep-alive',
    'proxy-authenticate', 'proxy-authorization', 'te', 'trailer',
]);

export const config = {
    api: {
        bodyParser: false,  // 手动处理 body，保持原始格式
    },
};

export default async function handler(req, res) {
    // CORS preflight
    if (req.method === 'OPTIONS') {
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', '*');
        res.setHeader('Access-Control-Max-Age', '86400');
        return res.status(204).end();
    }

    // CORS headers for all responses
    res.setHeader('Access-Control-Allow-Origin', '*');

    try {
        const { route } = req.query;  // [...route] from the filename

        if (!route || route.length < 2) {
            return res.status(400).json({
                error: 'Invalid proxy path. Use /api/proxy/<backend>/<path>',
                backends: Object.keys(BACKENDS),
            });
        }

        const backend = route[0];
        const remotePath = '/' + route.slice(1).join('/');

        if (!BACKENDS[backend]) {
            return res.status(400).json({
                error: `Unknown backend: ${backend}`,
                available: Object.keys(BACKENDS),
            });
        }

        // Preserve original query string
        const queryString = new URL(req.url, 'http://localhost').search;
        const targetUrl = BACKENDS[backend] + remotePath + queryString;

        // Forward headers (strip forbidden ones)
        const forwardHeaders = {};
        for (const [key, value] of Object.entries(req.headers)) {
            if (!FORBIDDEN_REQ_HEADERS.has(key.toLowerCase())) {
                forwardHeaders[key] = value;
            }
        }

        // Ensure correct Host header
        const targetHost = new URL(BACKENDS[backend]).host;
        forwardHeaders['host'] = targetHost;

        // Read raw body
        const chunks = [];
        for await (const chunk of req) {
            chunks.push(chunk);
        }
        const body = Buffer.concat(chunks);

        // Make the proxy request
        const fetchOptions = {
            method: req.method,
            headers: forwardHeaders,
        };

        if (req.method !== 'GET' && req.method !== 'HEAD' && body.length > 0) {
            fetchOptions.body = body;
        }

        const response = await fetch(targetUrl, fetchOptions);

        // Forward response status
        res.status(response.status);

        // Forward response headers
        for (const [key, value] of response.headers.entries()) {
            if (!FORBIDDEN_RES_HEADERS.has(key.toLowerCase())) {
                res.setHeader(key, value);
            }
        }

        // Stream response body
        const responseBuffer = Buffer.from(await response.arrayBuffer());
        res.end(responseBuffer);

    } catch (error) {
        console.error('Proxy error:', error);
        res.status(502).json({
            error: 'Proxy request failed',
            message: error.message,
        });
    }
}
