/** RAG management page - folders and documents. */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useDropzone } from "react-dropzone";
import Link from "next/link";
import { api, ApiError, type RagDocument, type RagFolder } from "@/lib/api";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { Button } from "@/components/shared/Button";
import { Input } from "@/components/shared/Input";

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
      const data = await api.listRagDocuments(
        agentId,
        selectedFolderId || undefined
      );
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
            selectedFolderId === f.id ? "bg-amber-100" : "hover:bg-gray-100"
          }`}
          style={{ paddingLeft: `${12 + depth * 16}px` }}
        >
          <button
            onClick={() => setSelectedFolderId(f.id)}
            className="flex-1 text-left px-2 py-2 truncate"
          >
            <span className={selectedFolderId === f.id ? "text-amber-900 font-medium" : ""}>
              {f.name}
            </span>
          </button>
          <div className="opacity-0 group-hover:opacity-100 flex gap-0.5 pr-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRenameFolder(f.id, f.name);
              }}
              className="p-1 text-gray-500 hover:text-gray-700 text-xs"
              title="Rename"
            >
              ✎
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDeleteFolder(f.id, f.name);
              }}
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

  const handleUpload = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of files) {
        await api.uploadRagDocument(
          agentId,
          file,
          selectedFolderId || undefined
        );
      }
      loadDocuments();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Failed to upload");
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleUpload,
    accept: {
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/pdf": [".pdf"],
      "image/*": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
    },
    multiple: true,
    disabled: uploading,
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
      <div className="w-56 shrink-0 border border-gray-200 rounded-lg bg-white p-3">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-gray-900">Folders</h3>
        </div>
        <button
          onClick={() => setSelectedFolderId(null)}
          className={`w-full text-left px-3 py-2 rounded-sm mb-1 ${
            selectedFolderId === null ? "bg-amber-100 text-amber-900" : "hover:bg-gray-100"
          }`}
        >
          All documents
        </button>
        {isLoadingFolders ? (
          <div className="flex justify-center py-4">
            <LoadingSpinner size="sm" />
          </div>
        ) : (
          <div className="space-y-0.5">
            {buildFolderTree(folders, handleRenameFolder, handleDeleteFolder)}
          </div>
        )}
        <div className="mt-3 flex gap-2">
          <Input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="New folder"
            className="flex-1 text-sm"
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

        {/* Upload zone */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
            isDragActive ? "border-amber-400 bg-amber-50" : "border-gray-300 bg-gray-50 hover:border-amber-300"
          } ${uploading ? "opacity-60 pointer-events-none" : ""}`}
        >
          <input {...getInputProps()} />
          {uploading ? (
            <p className="text-sm text-gray-600">Uploading...</p>
          ) : (
            <>
              <p className="text-sm font-medium text-gray-700">
                Drag & drop files here, or click to select
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Supports: .txt, .md, .pdf, images (.jpg, .png, .gif, .webp)
              </p>
            </>
          )}
        </div>

        {/* Document list */}
        <div className="mt-4 flex-1">
          {isLoadingDocs ? (
            <div className="flex justify-center py-12">
              <LoadingSpinner size="lg" />
            </div>
          ) : documents.length === 0 ? (
            <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
              <p className="text-gray-600">No documents yet. Upload files above.</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {documents.map((doc) => (
                <div
                  key={doc.document_id}
                  className="border border-gray-200 rounded-lg bg-white overflow-hidden"
                >
                  {doc.file_type === "image" && doc.file_url && (
                    <div className="aspect-video bg-gray-100">
                      <img
                        src={doc.file_url}
                        alt={doc.title}
                        className="w-full h-full object-contain"
                      />
                    </div>
                  )}
                  <div className="p-3">
                    <p className="font-medium text-gray-900 truncate" title={doc.title}>
                      {doc.title}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {doc.file_type} • {doc.original_filename || doc.document_id}
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
                          setDeleteModal({
                            type: "document",
                            id: doc.document_id,
                            name: doc.title,
                          })
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
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="font-semibold text-gray-900 mb-2">Delete permanently?</h3>
            <p className="text-sm text-gray-600 mb-4">
              This will permanently delete &quot;{deleteModal.name}&quot;. This action cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => setDeleteModal(null)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={handleDelete}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Rename modal */}
      {renameModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="font-semibold text-gray-900 mb-2">Rename</h3>
            <Input
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder={renameModal.type === "folder" ? "Folder name" : "Document title"}
              className="mb-4"
            />
            <div className="flex gap-2 justify-end">
              <Button variant="secondary" onClick={() => setRenameModal(null)}>
                Cancel
              </Button>
              <Button onClick={handleRename} disabled={!newFolderName.trim()}>
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
