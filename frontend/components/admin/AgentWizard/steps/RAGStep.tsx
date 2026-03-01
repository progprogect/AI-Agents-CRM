/** Step 3: RAG Documents. */

"use client";

import React, { useCallback, useState } from "react";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import { Toggle } from "@/components/shared/Toggle";
import { Input } from "@/components/shared/Input";
import { Textarea } from "@/components/shared/Textarea";
import { Button } from "@/components/shared/Button";
import type { AgentConfigFormData } from "@/lib/utils/agentConfig";
import type { ValidationError } from "@/lib/utils/validation";
import { getFieldError } from "@/lib/utils/validation";

interface RAGStepProps {
  config: Partial<AgentConfigFormData>;
  errors: ValidationError[];
  onUpdate: (config: Partial<AgentConfigFormData>) => void;
  agentId?: string;
}

export const RAGStep: React.FC<RAGStepProps> = ({
  config,
  errors,
  onUpdate,
  agentId,
}) => {
  const ragEnabled = config.rag_enabled || false;
  const documents = config.rag_documents || [];
  const [isProcessingFile, setIsProcessingFile] = useState(false);

  const handleToggleRAG = useCallback(
    (enabled: boolean) => {
      onUpdate({
        rag_enabled: enabled,
        rag_documents: enabled ? documents : [],
      });
    },
    [documents, onUpdate]
  );

  const processFile = async (file: File): Promise<{
    title: string;
    content: string;
  }> => {
    const title = file.name.replace(/\.[^/.]+$/, ""); // Remove extension

    // Handle PDF files
    if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) {
      try {
        // Dynamic import to avoid SSR issues
        const pdfjsLib = await import("pdfjs-dist");
        const pdfjs = pdfjsLib.default || pdfjsLib;
        
        // Set worker source for PDF.js (using CDN)
        if (typeof window !== "undefined" && pdfjs.GlobalWorkerOptions) {
          pdfjs.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version || "3.11.174"}/pdf.worker.min.js`;
        }
        
        const arrayBuffer = await file.arrayBuffer();
        const loadingTask = pdfjs.getDocument({ data: arrayBuffer });
        const pdf = await loadingTask.promise;
        
        let fullText = "";
        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const textContent = await page.getTextContent();
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const pageText = textContent.items
            .map((item: any) => (item.str || ""))
            .join(" ");
          fullText += pageText + "\n\n";
        }
        
        return { title, content: fullText.trim() };
      } catch (error) {
        console.error("Error processing PDF:", error);
        throw new Error(`Failed to process PDF: ${error instanceof Error ? error.message : "Unknown error"}`);
      }
    }

    // Handle text files
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        resolve({ title, content });
      };
      reader.onerror = reject;
      
      if (file.type === "text/plain" || file.type === "text/markdown" || file.type === "application/json") {
        reader.readAsText(file);
      } else {
        // Try to read as text anyway
        reader.readAsText(file);
      }
    });
  };

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!ragEnabled) {
        handleToggleRAG(true);
      }

      setIsProcessingFile(true);
      try {
        const newDocs = await Promise.all(
          acceptedFiles.map(async (file, index) => {
            try {
              const { title, content } = await processFile(file);
              return {
                id: `doc_${Date.now()}_${index}_${Math.random().toString(36).substring(2, 11)}`,
                title,
                content,
              };
            } catch (fileError) {
              console.error(`Error processing file ${file.name}:`, fileError);
              // Return a document with error message
              return {
                id: `doc_${Date.now()}_${index}_error`,
                title: `${file.name} (Error)`,
                content: `Error processing file: ${fileError instanceof Error ? fileError.message : "Unknown error"}`,
              };
            }
          })
        );

        onUpdate({
          rag_documents: [...documents, ...newDocs],
        });
      } catch (error) {
        console.error("Error processing files:", error);
      } finally {
        setIsProcessingFile(false);
      }
    },
    [documents, ragEnabled, onUpdate, handleToggleRAG]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/json": [".json"],
      "application/pdf": [".pdf"],
    },
    multiple: true,
  });

  const handleAddDocument = () => {
    const newDoc = {
      id: `doc_${Date.now()}`,
      title: "",
      content: "",
    };
    onUpdate({
      rag_documents: [...documents, newDoc],
    });
  };

  const handleRemoveDocument = (index: number) => {
    const updated = documents.filter((_, i) => i !== index);
    onUpdate({ rag_documents: updated });
  };

  const handleUpdateDocument = (
    index: number,
    field: "title" | "content",
    value: string
  ) => {
    const updated = documents.map((doc, i) =>
      i === index ? { ...doc, [field]: value } : doc
    );
    onUpdate({ rag_documents: updated });
  };

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Knowledge Base (RAG)
        </h3>
        <p className="text-sm text-gray-600 mb-6">
          Enable RAG to provide context-aware responses based on documents
          about the agent and company.
        </p>
      </div>

      <Toggle
        label="Enable RAG"
        checked={ragEnabled}
        onChange={handleToggleRAG}
        description="Retrieval-Augmented Generation allows the agent to use your documents for context-aware responses."
      />

      {agentId && ragEnabled && (
        <p className="text-sm text-gray-600 mt-2">
          <Link
            href={`/admin/agents/${agentId}/rag`}
            className="text-[#D4AF37] hover:text-[#B8860B] underline"
          >
            Manage documents
          </Link>
          {" "}— upload files, organize in folders, add images.
        </p>
      )}

      {!agentId && ragEnabled && (
        <p className="text-sm text-gray-500 mt-2 italic">
          You can add and manage documents after creating the agent.
        </p>
      )}

      {ragEnabled && (
        <div className="mt-6 space-y-6">
          <div className="flex items-center justify-between">
            <h4 className="text-md font-medium text-gray-900">Documents</h4>
            <div className="flex gap-2">
              <Button variant="primary" size="sm" onClick={handleAddDocument}>
                Add Document
              </Button>
            </div>
          </div>

          {/* Drag & Drop Zone */}
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-sm p-8 text-center cursor-pointer transition-all duration-200 ${
              isDragActive
                ? "border-[#D4AF37] bg-[#F5D76E]/10"
                : "border-gray-300 bg-gray-50 hover:border-[#D4AF37]/50 hover:bg-gray-100"
            }`}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center">
              <svg
                className="w-12 h-12 text-gray-400 mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
              {isDragActive ? (
                <p className="text-sm font-medium text-[#D4AF37]">
                  Drop files here...
                </p>
              ) : (
                <>
                  <p className="text-sm font-medium text-gray-700 mb-1">
                    Drag & drop files here, or click to select
                  </p>
                  <p className="text-xs text-gray-500">
                    Supports: .txt, .md, .json, .pdf files
                  </p>
                </>
              )}
            </div>
          </div>

          {isProcessingFile && (
            <div className="text-center py-4">
              <p className="text-sm text-gray-600">Processing files...</p>
            </div>
          )}

          {documents.length === 0 ? (
            <div className="text-center py-8 bg-gray-50 rounded-sm border border-gray-200">
              <p className="text-sm text-gray-600 mb-4">
                No documents added yet.
              </p>
              <Button variant="secondary" size="sm" onClick={handleAddDocument}>
                Add First Document Manually
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {documents.map((doc, index) => (
                <div
                  key={doc.id}
                  className="p-4 bg-gray-50 rounded-sm border border-gray-200"
                >
                  <div className="flex items-center justify-between mb-4">
                    <h5 className="text-sm font-medium text-gray-900">
                      Document {index + 1}
                    </h5>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => handleRemoveDocument(index)}
                    >
                      Remove
                    </Button>
                  </div>
                  <div className="space-y-4">
                    <Input
                      label="Title"
                      value={doc.title}
                      onChange={(e) =>
                        handleUpdateDocument(index, "title", e.target.value)
                      }
                      error={getFieldError(
                        errors,
                        `rag_documents[${index}].title`
                      )}
                      placeholder="About Agent"
                    />
                    <Textarea
                      label="Content"
                      value={doc.content}
                      onChange={(e) =>
                        handleUpdateDocument(index, "content", e.target.value)
                      }
                      error={getFieldError(
                        errors,
                        `rag_documents[${index}].content`
                      )}
                      placeholder="Enter document content here..."
                      rows={6}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}

          {getFieldError(errors, "rag_documents") && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-sm">
              <p className="text-sm text-red-600">
                {getFieldError(errors, "rag_documents")}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

