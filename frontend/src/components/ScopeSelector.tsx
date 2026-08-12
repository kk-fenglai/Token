import type { ProjectItem } from "../api/types";
import { useApi } from "../api/useApi";
import { useScope } from "../api/scope";
import { useI18n } from "../i18n";

export default function ScopeSelector() {
  const { t } = useI18n();
  const { project, setProject } = useScope();
  // Deliberately unscoped: the picker must always list every project.
  const projects = useApi<{ items: ProjectItem[] }>("/api/projects?range=all");

  return (
    <label className="flex items-center gap-2 text-xs text-on-surface-variant">
      <span className="material-symbols-outlined text-base">filter_alt</span>
      <span className="sr-only">{t("scope.label")}</span>
      <select
        value={project ?? ""}
        onChange={(e) => setProject(e.target.value || null)}
        className={`h-8 max-w-[220px] rounded border px-2 text-sm ${
          project
            ? "border-primary-container bg-primary-container/10 font-semibold text-primary-container"
            : "border-outline-variant bg-surface-card text-on-surface"
        }`}
        title={project ?? t("scope.allProjects")}
      >
        <option value="">{t("scope.allProjects")}</option>
        {projects.data?.items.map((p) => (
          <option key={p.path} value={p.path}>{p.name}</option>
        ))}
      </select>
    </label>
  );
}
