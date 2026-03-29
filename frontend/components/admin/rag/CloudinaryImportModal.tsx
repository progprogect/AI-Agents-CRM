/** Modal: browse Cloudinary assets and import into RAG (Cloudinary storage only). */

"use client";

import { useCallback, useEffect, useState } from "react";
import { Cloud, FileText, Image as ImageIcon, X } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  api,
  ApiError,
  type CloudinaryImportResultItem,
  type CloudinaryRagResource,
  type RagFolder,
} from "@/lib/api";
import { Button } from "@/components/shared/Button";
import { Input } from "@/components/shared/Input";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

function normalizePrefix(s: string): string {
  return s.trim().replace(/^\/+|\/+$/g, "");
}

function humanSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function resourceIcon(r: CloudinaryRagResource) {
  if (r.resource_type === "image")
    return <ImageIcon size={20} className="text-[#9A9590] shrink-0" aria-hidden />;
  return <FileText size={20} className="text-[#9A9590] shrink-0" aria-hidden />;
}

const MAX_BATCH = 20;

type Props = {
  agentId: string;
  folders: RagFolder[];
  initialFolderId: string | null;
  onClose: () => void;
  onImported: () => void;
};

export function CloudinaryImportModal({
  agentId,
  folders,
  initialFolderId,
  onClose,
  onImported,
}: Props) {
  const t = useTranslations("RagPage");
  const tCommon = useTranslations("Common");

  const [prefixInput, setPrefixInput] = useState("");
  const [listPrefix, setListPrefix] = useState("");
  const [resources, setResources] = useState<CloudinaryRagResource[]>([]);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [storageUnavailable, setStorageUnavailable] = useState(false);

  const [selectedById, setSelectedById] = useState<Map<string, CloudinaryRagResource>>(new Map());
  const [folderId, setFolderId] = useState<string | null>(initialFolderId);

  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<{ current: number; total: number } | null>(
    null
  );
  const [importResults, setImportResults] = useState<CloudinaryImportResultItem[] | null>(null);

  const selectedCount = selectedById.size;
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !importing) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [importing, onClose]);

  const fetchPage = useCallback(
    async (opts: { prefix?: string; append: boolean; cursor?: string | null }) => {
      setLoadError(null);
      setLoadingList(true);
      try {
        const params: { prefix?: string; max_results?: number; next_cursor?: string } = {
          max_results: 100,
        };
        const p = opts.prefix !== undefined ? normalizePrefix(opts.prefix) : undefined;
        if (p) params.prefix = p;
        if (opts.cursor) params.next_cursor = opts.cursor;

        const data = await api.listCloudinaryRagResources(agentId, params);

        const lp = p ?? normalizePrefix(data.default_prefix);
        setListPrefix(lp);

        setResources((prev) => (opts.append ? [...prev, ...data.resources] : data.resources));
        setNextCursor(data.next_cursor ?? null);
        if (typeof data.total_count === "number") {
          setTotalCount(data.total_count);
        } else if (!opts.append) {
          setTotalCount(null);
        }

        if (!opts.append) {
          setSelectedById(new Map());
          if (!opts.cursor && p === undefined) {
            setPrefixInput(data.default_prefix);
          }
        }
      } catch (err) {
        if (err instanceof ApiError && err.code === "501") {
          setStorageUnavailable(true);
          setLoadError(t("notAvailable"));
        } else if (err instanceof ApiError) {
          setLoadError(err.message);
        } else {
          setLoadError("Failed to load");
        }
      } finally {
        setLoadingList(false);
      }
    },
    [agentId, t]
  );

  useEffect(() => {
    setFolderId(initialFolderId);
  }, [initialFolderId]);

  useEffect(() => {
    fetchPage({ append: false });
  }, [fetchPage]);

  const handleLoadList = () => {
    const p = normalizePrefix(prefixInput);
    fetchPage({ prefix: p || undefined, append: false });
  };

  const handleLoadMore = () => {
    if (!nextCursor || loadingList || !listPrefix) return;
    fetchPage({
      prefix: listPrefix,
      append: true,
      cursor: nextCursor,
    });
  };

  const toggleOne = (r: CloudinaryRagResource) => {
    setSelectedById((prev) => {
      const next = new Map(prev);
      if (next.has(r.public_id)) next.delete(r.public_id);
      else next.set(r.public_id, r);
      return next;
    });
  };

  const selectAllOnPage = () => {
    setSelectedById((prev) => {
      const next = new Map(prev);
      for (const r of resources) {
        next.set(r.public_id, r);
      }
      return next;
    });
  };

  const clearSelection = () => setSelectedById(new Map());

  const runImport = async () => {
    const items = Array.from(selectedById.values());
    if (!items.length || !listPrefix) return;

    setImporting(true);
    setImportResults(null);
    setLoadError(null);
    const allResults: CloudinaryImportResultItem[] = [];
    const total = items.length;

    try {
      for (let i = 0; i < items.length; i += MAX_BATCH) {
        const chunk = items.slice(i, i + MAX_BATCH);
        setImportProgress({ current: i, total });
        const res = await api.importRagFromCloudinary(agentId, {
          items: chunk.map((r) => ({
            public_id: r.public_id,
            resource_type: r.resource_type,
            format: r.format ?? null,
          })),
          folder_id: folderId,
          allowed_prefix: listPrefix,
        });
        allResults.push(...res.results);
        const done = Math.min(i + chunk.length, total);
        setImportProgress({ current: done, total });
      }
      setImportResults(allResults);
      onImported();
    } catch (err) {
      if (err instanceof ApiError) setLoadError(err.message);
      else setLoadError("Import failed");
    } finally {
      setImporting(false);
      setImportProgress(null);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4 pt-[env(safe-area-inset-top,0px)]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cloudinary-import-title"
      onClick={() => {
        if (!importing) onClose();
      }}
    >
      <div
        className="bg-white border border-[#BEBAB7] rounded-t-sm sm:rounded-sm shadow-lg w-full sm:max-w-lg max-h-[min(100dvh,720px)] flex flex-col touch-manipulation pl-[max(1rem,env(safe-area-inset-left,0px))] pr-[max(1rem,env(safe-area-inset-right,0px))] pb-[max(0.75rem,env(safe-area-inset-bottom,0px))] sm:pl-0 sm:pr-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 px-0 sm:px-4 py-3 border-b border-[#EEEAE7] shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Cloud className="text-[#251D1C] shrink-0" size={22} aria-hidden />
            <h2 id="cloudinary-import-title" className="font-semibold text-gray-900 truncate">
              {t("cloudinaryModalTitle")}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-sm text-gray-500 hover:text-gray-800 hover:bg-[#EEEAE7]/80"
            aria-label={tCommon("close")}
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto overflow-x-hidden px-0 sm:px-4 py-3 space-y-4 min-h-0">
          {storageUnavailable && (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-sm p-3">
              {t("notAvailable")}
            </p>
          )}

          {loadError && !storageUnavailable && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-sm p-3">
              {loadError}
            </p>
          )}

          {!storageUnavailable && (
            <>
              <div>
                <label
                  htmlFor="rag-import-prefix"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  {t("prefixLabel")}
                </label>
                <Input
                  id="rag-import-prefix"
                  name="rag-import-prefix"
                  value={prefixInput}
                  onChange={(e) => setPrefixInput(e.target.value)}
                  className="text-base sm:text-sm w-full min-h-[44px]"
                  placeholder={listPrefix || "rag/…"}
                  disabled={loadingList || importing}
                  autoComplete="off"
                />
                <p className="text-xs text-gray-500 mt-1">{t("prefixHint")}</p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="mt-2 min-h-[44px]"
                  onClick={handleLoadList}
                  disabled={loadingList || importing}
                >
                  {t("loadList")}
                </Button>
              </div>

              <div>
                <label htmlFor="rag-import-folder" className="block text-sm font-medium text-gray-700 mb-1">
                  {t("targetFolder")}
                </label>
                <select
                  id="rag-import-folder"
                  className="w-full max-w-full rounded-sm border border-[#BEBAB7] bg-white px-3 py-2.5 text-base sm:text-sm text-gray-900 min-h-[44px]"
                  value={folderId ?? ""}
                  onChange={(e) => setFolderId(e.target.value || null)}
                  disabled={importing}
                >
                  <option value="">{t("folderRoot")}</option>
                  {folders.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="min-h-[44px]"
                  onClick={selectAllOnPage}
                  disabled={!resources.length || loadingList || importing}
                >
                  {t("selectAllPage")}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="min-h-[44px]"
                  onClick={clearSelection}
                  disabled={!selectedCount || importing}
                >
                  {t("clearSelection")}
                </Button>
                <span className="text-sm text-gray-600">{t("selectedCount", { count: selectedCount })}</span>
              </div>

              {totalCount != null && resources.length > 0 && (
                <p className="text-xs text-gray-500">
                  {t("cloudinaryListStats", { loaded: resources.length, total: totalCount })}
                </p>
              )}

              {loadingList && resources.length === 0 ? (
                <div className="flex justify-center py-8">
                  <LoadingSpinner size="md" />
                </div>
              ) : !resources.length && !loadingList ? (
                <p className="text-sm text-gray-600 py-4 text-center border border-dashed border-[#BEBAB7] rounded-sm">
                  {t("noResources")}
                </p>
              ) : (
                <ul className="space-y-2 border border-[#EEEAE7] rounded-sm divide-y divide-[#EEEAE7] max-h-[min(40vh,320px)] sm:max-h-[40vh] overflow-y-auto overscroll-contain">
                  {resources.map((r) => {
                    const checked = selectedById.has(r.public_id);
                    return (
                      <li key={r.public_id}>
                        <label className="flex gap-3 items-center min-h-[44px] p-3 bg-white cursor-pointer active:bg-[#EEEAE7]/40">
                          <input
                            type="checkbox"
                            className="h-5 w-5 shrink-0 rounded border-[#BEBAB7] accent-[#251D1C]"
                            checked={checked}
                            onChange={() => toggleOne(r)}
                            disabled={importing}
                            aria-label={r.public_id}
                          />
                          <div className="w-14 h-14 shrink-0 rounded-sm overflow-hidden bg-[#EEEAE7] flex items-center justify-center">
                            {r.resource_type === "image" && r.secure_url ? (
                              <img
                                src={r.secure_url}
                                alt=""
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              resourceIcon(r)
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 break-words">{r.public_id}</p>
                            <p className="text-xs text-gray-500 mt-0.5">
                              {t("type")}: {r.resource_type}
                              {r.format ? ` .${r.format}` : ""}
                              {typeof r.bytes === "number" ? ` • ${humanSize(r.bytes)}` : ""}
                            </p>
                          </div>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}

              {nextCursor && (
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full min-h-[44px]"
                  onClick={handleLoadMore}
                  disabled={loadingList || importing}
                  isLoading={loadingList && resources.length > 0}
                >
                  {t("loadMore")}
                </Button>
              )}
            </>
          )}
        </div>

        <div className="border-t border-[#EEEAE7] px-0 sm:px-4 py-3 space-y-2 shrink-0">
          {importProgress && (
            <p className="text-sm text-gray-600 text-center">
              {t("importing")} {importProgress.current}/{importProgress.total}
            </p>
          )}

          {importResults && importResults.length > 0 && (
            <div className="max-h-36 overflow-y-auto text-xs border border-[#EEEAE7] rounded-sm p-2 space-y-1 bg-[#FAFAF9]">
              <p className="font-medium text-gray-800 mb-1">{t("importDone")}</p>
              {importResults.map((row) => (
                <div key={row.public_id} className="flex gap-2 justify-between break-all">
                  <span className="text-gray-700 shrink min-w-0">{row.public_id}</span>
                  <span
                    className={
                      row.status === "ok"
                        ? "text-green-700 shrink-0"
                        : row.status === "duplicate"
                          ? "text-amber-700 shrink-0"
                          : "text-red-700 shrink-0"
                    }
                  >
                    {row.status === "ok"
                      ? t("statusOk")
                      : row.status === "duplicate"
                        ? t("statusDuplicate")
                        : t("statusError")}
                    {row.message ? `: ${row.message}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col sm:flex-row gap-3 sm:gap-2 sm:justify-end">
            <Button
              type="button"
              variant="secondary"
              className="min-h-[44px] w-full sm:w-auto"
              onClick={onClose}
              disabled={importing}
            >
              {tCommon("close")}
            </Button>
            {!storageUnavailable && (
              <Button
                type="button"
                className="min-h-[44px] w-full sm:w-auto"
                onClick={runImport}
                disabled={!selectedCount || importing || loadingList || !listPrefix}
                isLoading={importing}
              >
                {importing ? t("importing") : t("importToRag", { count: selectedCount })}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
