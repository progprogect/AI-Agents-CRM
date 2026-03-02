/** RAG management page - folders and documents with file preview. */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useDropzone } from "react-dropzone";
import Link from "next/link";
import { FileText, Image as ImageIcon, X, Upload, FolderOpen } from "lucide-react";
import { api, ApiError, type RagDocument, type RagFolder } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { Input } from "@/components/shared/Input";

interface PendingFile {
  file: File;
  preview: string | null; // object URL for images
}

function fileIcon(type: string) {
  if (type.startsWith("image/")) return <ImageIcon size={20} className="text-[#251D1C]" />;
  return <FileText size={20} className="text-[#9A9590]" />;
}

function humanSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function AgentRAGPage() {
  const params = useParams();
  const agentId = params.agentId as string;

  const [folders, setFolders] = useState<RagFolder[]>([]);
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const [isLoadingFolders, setIsLoadingFolders] = useState(true);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{current: number; total: number} | null>(null);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [uploadWarnings, setUploadWarnings] = useState<string[]>([]);
  const [deleteModal, setDeleteModal] = useState<{
    type: "folder" | "document";
    id: string;
    name: string;
  } | null>(null);
  const [renameModal, setRenameModal] = useState<{
    type: "folder" | "document";
    id: string;
    name: string;
  } | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadFolders = useCallback(async () => {
    try {
      setIsLoadingFolders(true);
      setError(null);
      const data = await api.listRagFolders(agentId);
      setFolders(data);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to load folders");
    } finally {
      setIsLoadingFolders(false);
    }
  }, [agentId]);

  const loadDocuments = useCallback(async () => {
    try {
      setIsLoadingDocs(true);
      setError(null);
      const data = await api.listRagDocuments(agentId, selectedFolderId || undefined);
      setDocuments(data);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to load documents");
    } finally {
      setIsLoadingDocs(false);
    }
  }, [agentId, selectedFolderId]);

  useEffect(() => {
    if (agentId) loadFolders();
  }, [agentId, loadFolders]);

  useEffect(() => {
    if (agentId) loadDocuments();
  }, [agentId, selectedFolderId, loadDocuments]);

  // Revoke object URLs on cleanup
  useEffect(() => {
    return () => {
      pendingFiles.forEach((pf) => { if (pf.preview) URL.revokeObjectURL(pf.preview); });
    };
  }, [pendingFiles]);

  const buildFolderTree = (
    items: RagFolder[],
    onRenameFolder: (id: string, name: string) => void,
    onDeleteFolder: (id: string, name: string) => void
  ) => {
    const byParent = new Map<string | null, RagFolder[]>();
    for (const f of items) {
      const pid = f.parent_id || null;
      if (!byParent.has(pid)) byParent.set(pid, []);
      byParent.get(pid)!.push(f);
    }
    const render = (parentId: string | null, depth: number): React.ReactNode[] => {
      const children = byParent.get(parentId) || [];
      return children.flatMap((f) => [
        <div
          key={f.id}
          className={`group flex items-center rounded-sm ${
            selectedFolderId === f.id ? "bg-[#EEEAE7] text-[#251D1C] font-medium" : "hover:bg-[#EEEAE7]/50"
          }`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
        >
          <button
            onClick={() => setSelectedFolderId(f.id)}
            className="flex-1 text-left px-2 py-2 truncate"
          >
            {f.name}
          </button>
          <div className="opacity-0 group-hover:opacity-100 flex gap-0.5 pr-1">
            <button
              onClick={(e) => { e.stopPropagation(); onRenameFolder(f.id, f.name); }}
              className="p-1 text-gray-500 hover:text-gray-700 text-xs"
              title="Rename"
            >
              ✎
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDeleteFolder(f.id, f.name); }}
              className="p-1 text-gray-500 hover:text-red-600 text-xs"
              title="Delete"
            >
              ×
            </button>
          </div>
        </div>,
        ...render(f.id, depth + 1),
      ]);
    };
    return render(null, 0);
  };

  const handleRenameFolder = (id: string, name: string) => {
    setRenameModal({ type: "folder", id, name });
    setNewFolderName(name);
  };

  const handleDeleteFolder = (id: string, name: string) => {
    setDeleteModal({ type: "folder", id, name });
  };

  const handleCreateFolder = async () => {
    const name = newFolderName.trim();
    if (!name) return;
    try {
      await api.createRagFolder(agentId, name, selectedFolderId || undefined);
      setNewFolderName("");
      loadFolders();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to create folder");
    }
  };

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const newPending: PendingFile[] = acceptedFiles.map((file) => ({
      file,
      preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
    }));
    setPendingFiles((prev) => [...prev, ...newPending]);
  }, []);

  const removePending = (index: number) => {
    setPendingFiles((prev) => {
      const item = prev[index];
      if (item.preview) URL.revokeObjectURL(item.preview);
      return prev.filter((_, i) => i !== index);
    });
  };

  const handleUploadAll = async () => {
    if (!pendingFiles.length) return;
    setUploading(true);
    setError(null);
    setUploadWarnings([]);
    setUploadProgress({ current: 0, total: pendingFiles.length });
    const warnings: string[] = [];
    try {
      for (let i = 0; i < pendingFiles.length; i++) {
        setUploadProgress({ current: i + 1, total: pendingFiles.length });
        const result = await api.uploadRagDocument(agentId, pendingFiles[i].file, selectedFolderId || undefined);
        // Check for partial success (document saved but AI processing failed)
        if (result && typeof result === "object" && "warning" in result) {
          warnings.push(`${pendingFiles[i].file.name}: ${(result as {warning: string}).warning}`);
        }
      }
      pendingFiles.forEach((pf) => { if (pf.preview) URL.revokeObjectURL(pf.preview); });
      setPendingFiles([]);
      if (warnings.length) setUploadWarnings(warnings);
      loadDocuments();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to upload");
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/json": [".json"],
      "application/pdf": [".pdf"],
      "image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"],
    },
    multiple: true,
    disabled: uploading,
    noClick: pendingFiles.length > 0, // when queue has files, only drag works; click add button instead
  });

  const handleDelete = async () => {
    if (!deleteModal) return;
    try {
      if (deleteModal.type === "folder") {
        await api.deleteRagFolder(agentId, deleteModal.id);
        if (selectedFolderId === deleteModal.id) setSelectedFolderId(null);
        loadFolders();
      } else {
        await api.deleteRagDocument(agentId, deleteModal.id);
        loadDocuments();
      }
      setDeleteModal(null);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to delete");
    }
  };

  const handleRename = async () => {
    if (!renameModal) return;
    const name = newFolderName.trim();
    if (!name) return;
    try {
      if (renameModal.type === "folder") {
        await api.updateRagFolder(agentId, renameModal.id, name);
        loadFolders();
      } else {
        await api.updateRagDocument(agentId, renameModal.id, { title: name });
        loadDocuments();
      }
      setRenameModal(null);
      setNewFolderName("");
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to rename");
    }
  };

  const openRename = (type: "folder" | "document", id: string, name: string) => {
    setRenameModal({ type, id, name });
    setNewFolderName(name);
  };

  return (
    <div className="flex gap-6 min-h-[600px]">
      {/* Left: Folders */}
      <div className="w-56 shrink-0 border border-[#BEBAB7] rounded-sm bg-white p-3">
        <div className="flex items-center gap-2 mb-3">
          <FolderOpen size={16} className="text-[#9A9590]" />
          <h3 className="font-semibold text-gray-900">Folders</h3>
        </div>
        <button
          onClick={() => setSelectedFolderId(null)}
          className={`w-full text-left px-3 py-2 rounded-sm mb-1 text-sm ${
            selectedFolderId === null
              ? "bg-[#EEEAE7] text-[#251D1C] font-medium"
              : "hover:bg-[#EEEAE7]/50 text-gray-700"
          }`}
        >
          All documents
        </button>
        {isLoadingFolders ? (
          <div className="flex justify-center py-4">
            <LoadingSpinner size="sm" />
          </div>
        ) : (
          <div className="space-y-0.5 text-sm">
            {buildFolderTree(folders, handleRenameFolder, handleDeleteFolder)}
          </div>
        )}
        <div className="mt-3 flex gap-2">
          <Input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="New folder"
            className="flex-1 text-sm"
            onKeyDown={(e) => e.key === "Enter" && handleCreateFolder()}
          />
          <Button size="sm" onClick={handleCreateFolder} disabled={!newFolderName.trim()}>
            Add
          </Button>
        </div>
      </div>

      {/* Main: Documents */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">RAG Documents</h1>
            <p className="text-sm text-gray-600 mt-1">
              Agent: {agentId}
              {selectedFolderId && (
                <span className="ml-2">
                  • Folder: {folders.find((f) => f.id === selectedFolderId)?.name}
                </span>
              )}
            </p>
          </div>
          <Link href={`/admin/agents/${agentId}`}>
            <Button variant="secondary">Back to Agent</Button>
          </Link>
        </div>

        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4 rounded-sm">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {uploadWarnings.length > 0 && (
          <div className="bg-amber-50 border-l-4 border-amber-400 p-4 mb-4 rounded-sm">
            <p className="text-sm font-medium text-amber-800 mb-1">
              Files saved, but AI processing failed:
            </p>
            <ul className="text-xs text-amber-700 space-y-1 list-disc list-inside">
              {uploadWarnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
            <p className="text-xs text-amber-600 mt-2">
              These files are stored but won&apos;t appear in semantic search. Check your Google AI Studio quota or switch to OpenAI embeddings.
            </p>
            <button
              onClick={() => setUploadWarnings([])}
              className="mt-2 text-xs text-amber-700 underline hover:text-amber-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Upload zone */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-sm p-5 text-center transition-all ${
            isDragActive
              ? "border-[#251D1C] bg-[#EEEAE7]"
              : "border-[#BEBAB7] bg-[#EEEAE7]/30 hover:border-[#443C3C]"
          } ${uploading ? "opacity-60 pointer-events-none" : "cursor-pointer"}`}
        >
          <input {...getInputProps()} />
          {uploading ? (
            <div className="flex flex-col items-center gap-2 py-2">
              <LoadingSpinner size="sm" />
              <p className="text-sm text-gray-600">
                {uploadProgress
                  ? `Uploading ${uploadProgress.current} of ${uploadProgress.total}...`
                  : "Uploading..."}
              </p>
            </div>
          ) : pendingFiles.length > 0 ? (
            <p className="text-sm text-gray-500">Drop more files here to add to queue</p>
          ) : (
            <>
              <Upload size={24} className="mx-auto mb-2 text-[#9A9590]" />
              <p className="text-sm font-medium text-gray-700">
                Drag & drop files here, or click to select
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Supports: .txt, .md, .json, .pdf, images (.jpg, .png, .gif, .webp)
              </p>
            </>
          )}
        </div>

        {/* Pending files queue */}
        {pendingFiles.length > 0 && (
          <div className="mt-3 border border-[#BEBAB7] rounded-sm bg-white overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#EEEAE7] bg-[#EEEAE7]/50">
              <p className="text-sm font-medium text-gray-700">
                Ready to upload ({pendingFiles.length} {pendingFiles.length === 1 ? "file" : "files"})
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    pendingFiles.forEach((pf) => { if (pf.preview) URL.revokeObjectURL(pf.preview); });
                    setPendingFiles([]);
                  }}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  Clear all
                </button>
                <Button size="sm" onClick={handleUploadAll} icon={<Upload size={14} />}>
                  Upload all
                </Button>
              </div>
            </div>
            <div className="divide-y divide-[#EEEAE7]">
              {pendingFiles.map((pf, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                  {/* Preview or icon */}
                  <div className="flex-shrink-0 w-12 h-12 rounded-sm overflow-hidden bg-[#EEEAE7] flex items-center justify-center">
                    {pf.preview ? (
                      <img
                        src={pf.preview}
                        alt={pf.file.name}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      fileIcon(pf.file.type)
                    )}
                  </div>
                  {/* File info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{pf.file.name}</p>
                    <p className="text-xs text-gray-500">{humanSize(pf.file.size)}</p>
                  </div>
                  {/* Remove */}
                  <button
                    onClick={() => removePending(i)}
                    className="flex-shrink-0 p-1 text-gray-400 hover:text-red-500 rounded-sm transition-colors"
                    aria-label="Remove from queue"
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Document list */}
        <div className="mt-4 flex-1">
          {isLoadingDocs ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          ) : documents.length === 0 ? (
            <div className="text-center py-12 bg-[#EEEAE7]/30 rounded-sm border border-[#BEBAB7]">
              <p className="text-gray-600">No documents yet. Upload files above.</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {documents.map((doc) => (
                <div
                  key={doc.document_id}
                  className="border border-[#BEBAB7] rounded-sm bg-white overflow-hidden hover:border-[#443C3C] transition-colors"
                >
                  {/* Image preview */}
                  {doc.file_type === "image" && doc.file_url ? (
                    <div className="aspect-video bg-[#EEEAE7]">
                      <img
                        src={doc.file_url}
                        alt={doc.title}
                        className="w-full h-full object-contain"
                      />
                    </div>
                  ) : (
                    <div className="flex items-center justify-center aspect-video bg-[#EEEAE7]/50">
                      <FileText size={32} className="text-[#BEBAB7]" />
                    </div>
                  )}
                  <div className="p-3">
                    <p className="font-medium text-gray-900 truncate text-sm" title={doc.title}>
                      {doc.title}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {doc.file_type}
                      {doc.file_size && ` • ${humanSize(doc.file_size)}`}
                    </p>
                    <div className="flex gap-2 mt-3">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => openRename("document", doc.document_id, doc.title)}
                      >
                        Rename
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        onClick={() =>
                          setDeleteModal({ type: "document", id: doc.document_id, name: doc.title })
                        }
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Delete modal */}
      {deleteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-sm p-6 max-w-md w-full mx-4 border border-[#BEBAB7]">
            <h3 className="font-semibold text-gray-900 mb-2">Delete permanently?</h3>
            <p className="text-sm text-gray-600 mb-4">
              This will permanently delete &quot;{deleteModal.name}&quot;. This action cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => setDeleteModal(null)}>Cancel</Button>
              <Button variant="danger" onClick={handleDelete}>Delete</Button>
            </div>
          </div>
        </div>
      )}

      {/* Rename modal */}
      {renameModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-sm p-6 max-w-md w-full mx-4 border border-[#BEBAB7]">
            <h3 className="font-semibold text-gray-900 mb-2">Rename</h3>
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder={renameModal.type === "folder" ? "Folder name" : "Document title"}
              className="mb-4"
              onKeyDown={(e) => e.key === "Enter" && handleRename()}
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => setRenameModal(null)}>Cancel</Button>
              <Button onClick={handleRename} disabled={!newFolderName.trim()}>Save</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
