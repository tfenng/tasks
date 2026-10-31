import { useEffect, useState } from "react";
import { Button, Card, Descriptions, Modal, Space, Table, Tag, Typography, message } from "antd";
import { Link, useNavigate, useParams } from "react-router-dom";
import dayjs from "dayjs";
import { cancelRun, getRun, retryRun } from "../api";
import type { Attempt, Run, User } from "../types";

export default function RunDetailPage({ user }: { user: User }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [outputAttempt, setOutputAttempt] = useState<Attempt | null>(null);

  function refresh() {
    if (!id) return;
    setLoading(true);
    getRun(id)
      .then(setRun)
      .catch((error) => message.error((error as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [id]);

  async function cancel() {
    if (!id) return;
    try {
      await cancelRun(id);
      message.success("已请求取消");
      refresh();
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  async function retry() {
    if (!id) return;
    try {
      const next = await retryRun(id);
      message.success("已创建重试运行");
      navigate(`/runs/${next.id}`);
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  if (!run) return <Card loading={loading} />;
  const config = run.executor_config || {};
  const command = run.executor_type === "local"
    ? (config.argv || []).join(" ")
    : run.executor_type === "ssh"
      ? config.command
      : `${config.method || "GET"} ${config.url || config.path || ""}`;

  return (
    <div>
      <div className="page-head">
        <Typography.Title level={3}>运行详情</Typography.Title>
        <Space>
          {user.role !== "viewer" && <Button onClick={cancel} disabled={["succeeded", "failed", "cancelled", "skipped", "missed"].includes(run.status)}>取消</Button>}
          {user.role !== "viewer" && <Button type="primary" onClick={retry} disabled={!["succeeded", "failed", "cancelled"].includes(run.status)}>重试</Button>}
        </Space>
      </div>
      <Card loading={loading}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="ID">{run.id}</Descriptions.Item>
          <Descriptions.Item label="状态"><Tag>{run.status}</Tag></Descriptions.Item>
          <Descriptions.Item label="任务定义">
            {run.definition_name ? <Link to={`/definitions/${run.definition_id}`}>{run.definition_name} ({run.definition_key})</Link> : run.definition_id}
          </Descriptions.Item>
          <Descriptions.Item label="定义版本">{run.definition_version_no ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="执行入口">{run.executor_type || "-"}</Descriptions.Item>
          <Descriptions.Item label="执行命令"><code>{command || "-"}</code></Descriptions.Item>
          <Descriptions.Item label="触发">{run.schedule_id ? `调度/${run.trigger_type}` : run.trigger_type}</Descriptions.Item>
          <Descriptions.Item label="尝试">{run.attempt_count}/{run.max_attempts}</Descriptions.Item>
          <Descriptions.Item label="调度 ID">{run.schedule_id || "-"}</Descriptions.Item>
          <Descriptions.Item label="计划时间">{run.scheduled_for ? dayjs(run.scheduled_for).format("YYYY-MM-DD HH:mm:ss") : "-"}</Descriptions.Item>
          <Descriptions.Item label="开始">{run.started_at ? dayjs(run.started_at).format("YYYY-MM-DD HH:mm:ss") : "-"}</Descriptions.Item>
          <Descriptions.Item label="结束">{run.finished_at ? dayjs(run.finished_at).format("YYYY-MM-DD HH:mm:ss") : "-"}</Descriptions.Item>
          <Descriptions.Item label="错误">{run.error_code || "-"}</Descriptions.Item>
          <Descriptions.Item label="下一次重试">{run.next_retry_at ? dayjs(run.next_retry_at).format("YYYY-MM-DD HH:mm:ss") : "-"}</Descriptions.Item>
          <Descriptions.Item label="调用参数" span={2}>
            <pre>{(run.arguments || []).join(" ") || "-"}</pre>
          </Descriptions.Item>
        </Descriptions>
        <Typography.Title level={4} style={{ marginTop: 24 }}>执行尝试</Typography.Title>
        <Table
          rowKey="id"
          dataSource={run.attempts || []}
          pagination={false}
          columns={[
            { title: "#", dataIndex: "attempt_no" },
            { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
            { title: "退出码", dataIndex: "exit_code", render: (value: number | null) => value ?? "-" },
            { title: "错误", dataIndex: "error_class", render: (value: string | null) => value || "-" },
            { title: "耗时(ms)", dataIndex: "duration_ms", render: (value: number | null) => value ?? "-" },
            {
              title: "输出",
              dataIndex: "stdout_excerpt",
              render: (value: string | null, attempt: Attempt) => {
                const stdout = (value || "").trim();
                const stderr = (attempt.stderr_excerpt || "").trim();
                if (!stdout && !stderr) return "-";
                const preview = (stdout || `[stderr] ${stderr}`).split("\n")[0];
                return (
                  <Space size={4}>
                    <span className="output-preview" title={preview}>
                      {preview}
                    </span>
                    <Button type="link" size="small" onClick={() => setOutputAttempt(attempt)}>
                      查看
                    </Button>
                  </Space>
                );
              },
            },
          ]}
        />
      </Card>
      <Modal
        title={outputAttempt ? `第 ${outputAttempt.attempt_no} 次尝试输出` : "执行输出"}
        open={outputAttempt !== null}
        onCancel={() => setOutputAttempt(null)}
        footer={null}
        width={880}
      >
        {outputAttempt && (
          <>
            <Space wrap style={{ marginBottom: 16 }}>
              <Tag>{outputAttempt.status}</Tag>
              <span>退出码：{outputAttempt.exit_code ?? "-"}</span>
              <span>耗时：{outputAttempt.duration_ms ?? "-"} ms</span>
              {outputAttempt.truncated && <Tag color="orange">输出已截断</Tag>}
            </Space>
            {outputAttempt.error_message && (
              <Typography.Paragraph type="danger" style={{ whiteSpace: "pre-wrap" }}>
                {outputAttempt.error_message}
              </Typography.Paragraph>
            )}
            <Typography.Title level={5}>标准输出</Typography.Title>
            <pre className="output" style={{ maxHeight: "40vh" }}>
              {outputAttempt.stdout_excerpt || "(空)"}
            </pre>
            <Typography.Title level={5} style={{ marginTop: 16 }}>
              错误输出
            </Typography.Title>
            <pre className="output" style={{ maxHeight: "40vh" }}>
              {outputAttempt.stderr_excerpt || "(空)"}
            </pre>
          </>
        )}
      </Modal>
    </div>
  );
}
