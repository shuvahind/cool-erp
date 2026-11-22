import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import { useReadUsersUsersGet } from "@/api/generated/users/users";

import {
  useListAccessAuditApiV1AuditAccessGet,
  useListDataAuditApiV1AuditDataGet,
} from "@/api/generated/audit-access-logs/audit-access-logs";

interface AuditPageProps {
  className?: string;
}

const getEntityTypeName = (entityType: string): string => {
  const entityNames: Record<string, string> = {
    note: "Заметки",
    section: "Разделы",
    user: "Пользователи",
    role: "Роли",
    goods: "Товары",
    warehouse: "Склады",
    tenant: "Организации",
    doctype: "Типы документов",
  };
  return entityNames[entityType] || entityType;
};

// ✅ Вспомогательная функция для красивого вывода длинных значений
const formatAuditValue = (val: any) => {
  if (val === null || val === undefined || val === "") return "пусто";
  if (Array.isArray(val)) {
    if (val.length === 0) return "пусто";
    return val.join(", "); // Выводим элементы через запятую
  }
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
};

// ✅ ВЫНЕСЕННЫЙ КОМПОНЕНТ ДЛЯ АККОРДЕОНА
const AuditChangesCell = ({ 
  changes, 
  action 
}: { 
  changes: Record<string, any>; 
  action: string;
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const entries = Object.entries(changes);
  const LIMIT = 3;

  const hasMore = entries.length > LIMIT;
  const visibleEntries = isExpanded ? entries : entries.slice(0, LIMIT);

  const renderNewValue = (text: string) => {
    if (text.includes("[Удалено]") || text.includes("[Добавлен]")) {
      const parts = text.split(/(?=\[Добавлен\]|\[Удалено\])/g);
      return parts.map((part, idx) => {
        const trimmed = part.trim();
        if (trimmed.startsWith("[Удалено]")) {
          return (
            <div key={idx} className="flex items-start gap-1 mb-1">
              <Badge
                variant="destructive"
                className="text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0"
              >
                Удалено
              </Badge>
              <span className="text-gray-500 break-words">
                {trimmed.replace("[Удалено]", "").trim()}
              </span>
            </div>
          );
        }
        if (trimmed.startsWith("[Добавлен]")) {
          return (
            <div key={idx} className="flex items-start gap-1 mb-1">
              <Badge
                variant="default"
                className="bg-green-600 text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0"
              >
                Добавлен
              </Badge>
              <span className="text-green-700 font-medium break-words">
                {trimmed.replace("[Добавлен]", "").trim()}
              </span>
            </div>
          );
        }
        return (
          <div key={idx} className="mb-1 break-words">
            {trimmed}
          </div>
        );
      });
    }
    return (
      <span className="text-green-600 font-medium break-words">{text}</span>
    );
  };

  return (
    <div className="space-y-1 text-xs w-full">
      <div className="w-full">
        {visibleEntries.map(([field, val]: [string, any]) => {
          const oldVal = formatAuditValue(val?.old);
          const newVal = formatAuditValue(val?.new);
          
          const isNewEmpty = newVal === "пусто";
          const isOldEmpty = oldVal === "пусто";

          return (
            <div
              key={field}
              className="mb-2 border-b border-gray-100 pb-1 last:border-0 last:pb-0"
            >
              <div className="font-semibold text-gray-700 mb-0.5">{field}:</div>
              <div className="flex flex-col gap-1">
                {/* 1. Вывод СТАРОГО значения */}
                {action !== "create" && !isOldEmpty && (
                  <div className="text-gray-400 text-[10px] mb-1 break-words whitespace-pre-wrap">
                    {oldVal}
                  </div>
                )}

                {/* 2. Вывод НОВОГО значения */}
                {action === "update" ? (
                  // При обновлении: если пусто — пишем "Удалено" красным
                  <div className="break-words whitespace-pre-wrap">
                    {isNewEmpty ? (
                      <div className="flex items-start gap-1 mb-1">
                        <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0">
                          Удалено
                        </Badge>
                      </div>
                    ) : (
                      renderNewValue(newVal)
                    )}
                  </div>
                ) : (
                  // При create: показываем только если не пусто. При delete: не показываем вообще (и так всё понятно из "Удалено")
                  action !== "delete" && !isNewEmpty && (
                    <div className="break-words whitespace-pre-wrap">
                      {renderNewValue(newVal)}
                    </div>
                  )
                )}
              </div>
            </div>
          );
        })}
      </div>

      {hasMore && (
        <Button
          variant="link"
          size="sm"
          className="text-xs h-6 px-0 text-blue-600 mt-1 font-semibold"
          onClick={() => setIsExpanded((v) => !v)}
        >
          {isExpanded ? "Свернуть" : `Показать все (${entries.length - LIMIT})`}
        </Button>
      )}
    </div>
  );
};

export const AuditPage = ({ className }: AuditPageProps) => {
  const [activeTab, setActiveTab] = useState<"access" | "data">("access");
  const [page, setPage] = useState(0);
  const [entityTypeFilter, setEntityTypeFilter] = useState<string | undefined>(
    undefined,
  );
  const [actionFilter, setActionFilter] = useState<string | undefined>(
    undefined,
  );

  const entityTypeOptions = [
    { value: undefined, label: "Все типы" },
    { value: "note", label: "Заметки" },
    { value: "goods", label: "Товары" },
    { value: "warehouse", label: "Склады" },
    { value: "user", label: "Пользователи" },
    { value: "section", label: "Разделы" },
    { value: "role", label: "Роли" },
  ];

  const actionOptions = [
    { value: undefined, label: "Все действия" },
    { value: "create", label: "Создание" },
    { value: "update", label: "Обновление" },
    { value: "delete", label: "Удаление" },
  ];

  const { data: users } = useReadUsersUsersGet();
  const userItems = (users as any)?.items || (users as any)?.data?.items || [];
  const [userEmailFilter, setUserEmailFilter] = useState<string | undefined>(
    undefined,
  );
  const [startDate, setStartDate] = useState<string | undefined>(undefined);
  const [endDate, setEndDate] = useState<string | undefined>(undefined);

  const {
    data: accessLogs,
    isLoading: isLoadingAccess,
    refetch: refetchAccess,
  } = useListAccessAuditApiV1AuditAccessGet(
    {
      skip: page * 20,
      limit: 20,
    },
    {
      query: {
        refetchOnMount: "always",
      },
    },
  );

  const {
    data: dataChanges,
    isLoading: isLoadingData,
    refetch: refetchData,
  } = useListDataAuditApiV1AuditDataGet(
    {
      skip: page * 20,
      limit: 20,
      entity_type: entityTypeFilter,
      action: actionFilter,
      user_email: userEmailFilter,
      start_date: startDate,
      end_date: endDate,
    },
    {
      query: {
        refetchOnMount: "always",
      },
    },
  );

  const handleRefresh = () => {
    if (activeTab === "access") {
      refetchAccess();
    } else {
      refetchData();
    }
  };

  const handleExport = async () => {
    const params = new URLSearchParams();
    if (entityTypeFilter) params.append("entity_type", entityTypeFilter);
    if (actionFilter) params.append("action", actionFilter);
    if (userEmailFilter) params.append("user_email", userEmailFilter);
    if (startDate) params.append("start_date", startDate);
    if (endDate) params.append("end_date", endDate);

    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const response = await fetch(
        `${baseUrl}/api/v1/audit/export?${params.toString()}`,
        {
          credentials: "include",
        },
      );

      if (!response.ok) {
        alert("Ошибка при экспорте данных");
        return;
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Ошибка экспорта:", error);
      alert("Не удалось скачать файл");
    }
  };

  return (
    <div className={`p-6 w-full max-w-full overflow-hidden ${className}`}>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Аудит</h1>
        <div className="flex gap-2">
          <Button onClick={handleRefresh} variant="outline">
            Обновить
          </Button>
          {activeTab === "data" && (
            <Button onClick={handleExport} variant="outline">
              Экспорт в CSV
            </Button>
          )}
        </div>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as "access" | "data")}
      >
        <TabsList>
          <TabsTrigger value="access">Логи входа</TabsTrigger>
          <TabsTrigger value="data">Изменения данных</TabsTrigger>
        </TabsList>

        <TabsContent value="access">
          {activeTab === "access" && (
            <>
              {isLoadingAccess ? (
                <div className="text-center py-8">Загрузка...</div>
              ) : accessLogs?.data?.items?.length ? (
                <div className="w-full overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Пользователь</TableHead>
                        <TableHead>Действие</TableHead>
                        <TableHead>Ресурс</TableHead>
                        <TableHead>Статус</TableHead>
                        <TableHead>IP</TableHead>
                        <TableHead>Дата</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {accessLogs.data.items.map((log: any) => (
                        <TableRow key={log.id}>
                          <TableCell>{log.user_email || "Система"}</TableCell>
                          <TableCell>{log.action}</TableCell>
                          <TableCell>{log.resource}</TableCell>
                          <TableCell>
                            <Badge
                              variant={
                                log.status === "success"
                                  ? "default"
                                  : "destructive"
                              }
                              className={
                                log.status === "success"
                                  ? "bg-green-600 text-white hover:bg-green-700"
                                  : ""
                              }
                            >
                              {log.status}
                            </Badge>
                          </TableCell>
                          <TableCell>{log.ip_address}</TableCell>
                          <TableCell>
                            {new Date(log.created_at).toLocaleString()}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-8">Логов пока нет</div>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="data">
          {activeTab === "data" && (
            <>
              <div className="flex flex-wrap gap-4 mb-4">
                {/* 3. Поиск по email */}
                <Combobox
                  value={userEmailFilter || ""}
                  onValueChange={(value) => {
                    setUserEmailFilter(value || undefined);
                    setPage(0);
                  }}
                  options={userItems}
                  getOptionLabel={(user: any) => user?.email || ""}
                  getOptionValue={(user: any) => user?.email || ""}
                  placeholder="Поиск по email"
                  className="w-[240px]"
                />

                {/* 1. Тип сущности */}
                <Select
                  value={entityTypeFilter || "undefined"}
                  onValueChange={(value) => {
                    setEntityTypeFilter(
                      value === "undefined" ? undefined : value,
                    );
                    setPage(0);
                  }}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Тип сущности" />
                  </SelectTrigger>
                  <SelectContent>
                    {entityTypeOptions.map((option) => (
                      <SelectItem
                        key={option.value || "all"}
                        value={option.value || "undefined"}
                      >
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* 2. Действие */}
                <Select
                  value={actionFilter || "undefined"}
                  onValueChange={(value) => {
                    setActionFilter(value === "undefined" ? undefined : value);
                    setPage(0);
                  }}
                >
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Действие" />
                  </SelectTrigger>
                  <SelectContent>
                    {actionOptions.map((option) => (
                      <SelectItem
                        key={option.value || "all"}
                        value={option.value || "undefined"}
                      >
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* 4. Дата С */}
                <div className="flex items-center gap-2">
                  <span>С</span>
                  <Input
                    type="date"
                    value={startDate || ""}
                    onChange={(e) => {
                      setStartDate(e.target.value || undefined);
                      setPage(0);
                    }}
                    className="w-[150px]"
                  />
                </div>

                {/* 5. Дата По */}
                <div className="flex items-center gap-2">
                  <span>По</span>
                  <Input
                    type="date"
                    value={endDate || ""}
                    onChange={(e) => {
                      setEndDate(e.target.value || undefined);
                      setPage(0);
                    }}
                    className="w-[150px]"
                  />
                </div>
              </div>

              {isLoadingData ? (
                <div className="text-center py-8">Загрузка...</div>
              ) : dataChanges?.data?.items?.length ? (
                <div className="w-full overflow-x-auto rounded-md border">
                  {/* ✅ table-fixed держит колонки на месте */}
                  <Table className="table-fixed w-full min-w-[800px]">
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[15%]">Пользователь</TableHead>
                        <TableHead className="w-[20%]">Сущность</TableHead>
                        <TableHead className="w-[10%]">Действие</TableHead>
                        <TableHead className="w-[45%]">Изменения</TableHead>
                        <TableHead className="w-[10%]">Дата</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {dataChanges.data.items.map((change: any) => (
                        <TableRow key={change.id}>
                          <TableCell className="align-top truncate">
                            {change.user_email || "Система"}
                          </TableCell>
                          <TableCell className="align-top truncate whitespace-normal break-words">
                            {change.entity_name
                              ? `${getEntityTypeName(change.entity_type)}: ${change.entity_name}`
                              : `${getEntityTypeName(change.entity_type)}: ${change.entity_id}`}
                          </TableCell>
                          <TableCell className="align-top">
                            {change.action}
                          </TableCell>

                          {/* ✅ ИСПОЛЬЗУЕМ НОВЫЙ КОМПОНЕНТ ЗДЕСЬ */}
                          <TableCell className="align-top break-words whitespace-normal">
                            {change.changes ? (
                              <AuditChangesCell
                                changes={change.changes as Record<string, any>}
                                action={change.action}
                              />
                            ) : (
                              <span className="text-muted-foreground">
                                Нет изменений
                              </span>
                            )}
                          </TableCell>

                          <TableCell className="align-top whitespace-nowrap text-xs">
                            {new Date(change.created_at).toLocaleString()}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <div className="text-center py-8">Логов пока нет</div>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>

      <div className="flex justify-center mt-6 space-x-4">
        <Button
          onClick={() => setPage(page - 1)}
          disabled={page === 0}
          variant="outline"
        >
          Назад
        </Button>
        <Button onClick={() => setPage(page + 1)} variant="outline">
          Вперед
        </Button>
      </div>
    </div>
  );
};