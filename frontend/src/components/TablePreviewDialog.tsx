import { api } from "../api/client";
import type { Artifact } from "../types";
import { useApi } from "../hooks/useApi";
import { formatFileSize } from "../utils/format";
import { ErrorBlock, LoadingBlock } from "./Common";
import { Modal } from "./Modal";

export function TablePreviewDialog({
  artifact,
  onClose,
}: {
  artifact: Artifact;
  onClose: () => void;
}) {
  const state = useApi(() => api.tablePreview(artifact.id), [artifact.id]);

  return (
    <Modal
      title={`表格预览：${artifact.path.split("/").pop()}`}
      subtitle={`最多显示 200 行、40 列；完整内容请下载。文件大小 ${formatFileSize(artifact.size)}。`}
      onClose={onClose}
      wide
    >
      {state.loading ? <LoadingBlock label="正在读取表格…" /> : null}
      {state.error ? <ErrorBlock error={state.error} onRetry={state.reload} /> : null}
      {state.data ? (
        <>
          {state.data.truncated ? (
            <p className="notice">表格内容已截断，仅显示前 200 行或前 40 列。</p>
          ) : null}
          <div className="table-scroll table-preview">
            <table className="data-table">
              <thead>
                <tr>
                  {state.data.columns.map((column, index) => (
                    <th key={`${column}-${index}`} scope="col">
                      {column || `第 ${index + 1} 列`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {state.data.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="dialog-actions">
            <a className="button" href={artifact.download_url} download>
              下载原始文件
            </a>
          </div>
        </>
      ) : null}
    </Modal>
  );
}
