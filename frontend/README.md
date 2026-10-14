# React + TypeScript + Vite

## 后端服务地址配置

默认后端地址在前端目录的 `.env` 文件中配置：

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

请求模块与设置页面统一读取此配置，不再在代码中维护默认地址。

- 修改 `.env` 后需要重启前端开发服务；生产部署需要重新构建前端。
- 如需区分环境，可在 `.env.development`、`.env.production` 中设置同名变量；本机配置可放在已被 Git 忽略的 `.env.local` 中。
- 设置页面保存的自定义地址会覆盖环境配置，仅对当前浏览器中的当前站点生效。点击「恢复默认」即可清除自定义地址，重新使用环境配置。
- 单次请求显式传入的 `baseUrl` 优先于上述两种配置。

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type aware lint rules:

- Configure the top-level `parserOptions` property like this:

```js
export default tseslint.config({
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
})
```

- Replace `tseslint.configs.recommended` to `tseslint.configs.recommendedTypeChecked` or `tseslint.configs.strictTypeChecked`
- Optionally add `...tseslint.configs.stylisticTypeChecked`
- Install [eslint-plugin-react](https://github.com/jsx-eslint/eslint-plugin-react) and update the config:

```js
// eslint.config.js
import react from 'eslint-plugin-react'

export default tseslint.config({
  // Set the react version
  settings: { react: { version: '18.3' } },
  plugins: {
    // Add the react plugin
    react,
  },
  rules: {
    // other rules...
    // Enable its recommended rules
    ...react.configs.recommended.rules,
    ...react.configs['jsx-runtime'].rules,
  },
})
```
