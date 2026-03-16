import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './shell/AppShell.tsx'
import { HomePage } from '../pages/HomePage.tsx'
import { IngestPage } from '../pages/IngestPage.tsx'
import { SearchPage } from '../pages/SearchPage.tsx'
import { EmbeddingFilePage } from '../pages/EmbeddingFile.tsx'
import { SettingsPage } from '../pages/SettingsPage.tsx'

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="ingest" element={<IngestPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="embedding-file" element={<EmbeddingFilePage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

