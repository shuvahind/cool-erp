import { useState } from "react";
import { format } from "date-fns";
import { ru } from "date-fns/locale";
import type { DateRange } from "react-day-picker";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ReferenceSelect, type ReferenceItem } from "@/lib/reusable/ReferenceSelect";
import { readUsersUsersGet } from "@/api/generated/users/users";
import { useListAccessAuditApiV1AuditAccessGet } from "@/api/generated/audit-access-logs/audit-access-logs";
import { User, X, CalendarIcon, Settings2, Search, LogIn, LogOut } from "lucide-react";
import { AuditPagination } from "./AuditPagination";
import { AuditHeader } from "./AuditHeader"; // ✅ ИМПОРТ ШАПКИ
import React from "react";
import { ShieldAlert } from "lucide-react";

interface AuditAccessTabProps {
    activeTab: "access" | "data";
    onTabChange: (value: "access" | "data") => void;
}

export const AuditAccessTab = ({ activeTab, onTabChange }: AuditAccessTabProps) => {
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(20);
    const [jumpInput, setJumpInput] = useState("");

    const [userEmailFilter, setUserEmailFilter] = useState<string | undefined>(undefined);
    const [actionFilter, setActionFilter] = useState<string | undefined>(undefined);
    const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
    const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);

    const startDate = dateRange?.from ? format(dateRange.from, "yyyy-MM-dd") : undefined;
    const endDate = dateRange?.to ? format(dateRange.to, "yyyy-MM-dd") : undefined;
    const skip = (page - 1) * pageSize;

    const { data, isLoading, isFetching, refetch } = useListAccessAuditApiV1AuditAccessGet(
        {
            skip,
            limit: pageSize,
            user_email: userEmailFilter,
            action: actionFilter,
            status: statusFilter,
            start_date: startDate,
            end_date: endDate,
        } as any,
        { query: { refetchOnMount: "always" } },
    );

    const total = (data?.data as any)?.total || 0;
    const items = data?.data?.items ?? [];

    const handleExport = async () => {
        const params = new URLSearchParams();
        if (userEmailFilter) params.append("user_email", userEmailFilter);
        if (actionFilter) params.append("action", actionFilter);
        if (statusFilter) params.append("status", statusFilter);
        if (startDate) params.append("start_date", startDate);
        if (endDate) params.append("end_date", endDate);

        try {
            const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
            const response = await fetch(`${baseUrl}/api/v1/audit/export/access?${params.toString()}`, {
                credentials: "include",
            });

            if (!response.ok) {
                alert("Ошибка при экспорте данных");
                return;
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `access_audit_${new Date().toISOString().slice(0, 10)}.csv`;
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
        <div className="flex flex-col h-full gap-4">
            {/* ✅ Используем вынесенную шапку */}
            <AuditHeader
                activeTab={activeTab}
                onTabChange={onTabChange}
                total={total}
                isFetching={isFetching}
                onRefresh={refetch}
                onExport={handleExport}
            />

            {/* Фильтры */}
            <div className="bg-card border rounded-lg p-3 flex flex-wrap gap-3 items-center shadow-sm shrink-0">
                {/* Пользователь */}
                <div className="flex items-center gap-2 border rounded-md px-3 h-9 bg-background w-[320px] shrink-0">
                    <User className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-[180px]">
                        <ReferenceSelect
                            fetchFn={async (params) => {
                                const response = await readUsersUsersGet({ skip: params.skip, limit: params.limit, search: params.search });
                                const items: ReferenceItem[] = (response?.data?.items ?? []).map((u: any) => ({ id: u.email, name: u.email, description: u.name }));
                                return { items, total: response?.data?.total ?? 0 };
                            }}
                            queryKey={["users-for-access-filter"]}
                            value={userEmailFilter || ""}
                            onValueChange={(value) => { setUserEmailFilter(value || undefined); setPage(1); }}
                            placeholder="Все пользователи"
                            selectedLabel={userEmailFilter || "Все пользователи"}
                            heading="Выберите пользователя"
                            columns={[{ column: "description", label: "Имя" }]}
                        />
                    </div>
                    {userEmailFilter && (
                        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground" onClick={() => { setUserEmailFilter(undefined); setPage(1); }}>
                            <X className="h-3 w-3" />
                        </Button>
                    )}
                </div>

                {/* Действие */}
                <div className="flex items-center gap-2 border rounded-md px-3 h-9 bg-background w-[180px] shrink-0">
                    <Settings2 className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                        <select
                            value={actionFilter || ""}
                            onChange={(e) => { setActionFilter(e.target.value || undefined); setPage(1); }}
                            className="w-full bg-transparent border-none outline-none text-sm"
                        >
                            <option value="">Все действия</option>
                            <option value="login">Вход</option>
                            <option value="logout">Выход</option>
                            <option value="access_denied">Доступ запрещен</option>
                        </select>
                    </div>
                    {actionFilter && (
                        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground" onClick={() => { setActionFilter(undefined); setPage(1); }}>
                            <X className="h-3 w-3" />
                        </Button>
                    )}
                </div>

                {/* Статус */}
                <div className="flex items-center gap-2 border rounded-md px-3 h-9 bg-background w-[180px] shrink-0">
                    <Search className="h-4 w-4 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                        <select
                            value={statusFilter || ""}
                            onChange={(e) => { setStatusFilter(e.target.value || undefined); setPage(1); }}
                            className="w-full bg-transparent border-none outline-none text-sm"
                        >
                            <option value="">Все статусы</option>
                            <option value="success">Успешно</option>
                            <option value="fail">Ошибка</option>
                        </select>
                    </div>
                    {statusFilter && (
                        <Button variant="ghost" size="icon" className="h-6 w-6 shrink-0 text-muted-foreground hover:text-foreground" onClick={() => { setStatusFilter(undefined); setPage(1); }}>
                            <X className="h-3 w-3" />
                        </Button>
                    )}
                </div>

                {/* Период */}
                <div className="flex items-center border rounded-md bg-background shrink-0 h-9">
                    <Popover>
                        <PopoverTrigger asChild>
                            <Button variant="ghost" className={`w-[220px] justify-start text-left font-normal px-3 h-full ${!dateRange?.from && "text-muted-foreground"}`}>
                                <CalendarIcon className="mr-2 h-4 w-4" />
                                {dateRange?.from ? (
                                    dateRange.to ? (
                                        <>{format(dateRange.from, "dd.MM.yyyy", { locale: ru })} — {format(dateRange.to, "dd.MM.yyyy", { locale: ru })}</>
                                    ) : (
                                        format(dateRange.from, "dd.MM.yyyy", { locale: ru })
                                    )
                                ) : (
                                    <span>Выберите период</span>
                                )}
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0" align="start">
                            <div className="p-3 px-4">
                                <Calendar
                                    mode="range"
                                    defaultMonth={dateRange?.from}
                                    selected={dateRange}
                                    onSelect={(range) => { setDateRange(range); setPage(1); }}
                                    numberOfMonths={2}
                                    locale={ru}
                                    className="[--cell-size:2rem] [&_.rdp-month]:w-full [&_.rdp-table]:w-full [&_.rdp-head_cell]:w-7 [&_.rdp-head_cell]:text-[0.65rem] [&_.rdp-cell]:w-7 [&_.rdp-cell]:h-7 [&_.rdp-cell]:p-0.5 [&_.rdp-day]:w-7 [&_.rdp-day]:h-7 [&_.rdp-day]:text-[0.7rem] [&_.rdp-caption_label]:text-xs [&_.rdp-caption_label]:font-medium [&_.rdp-month_caption]:mb-1 [&_.rdp-months]:gap-4 [&_.rdp-row]:gap-0.5 [&_.rdp-day_range_start]:rounded-l-md [&_.rdp-day_range_end]:rounded-r-md"
                                />
                            </div>
                        </PopoverContent>
                    </Popover>
                    {dateRange?.from && (
                        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground mr-1" onClick={() => { setDateRange(undefined); setPage(1); }}>
                            <X className="h-4 w-4" />
                        </Button>
                    )}
                </div>

                {(userEmailFilter || actionFilter || statusFilter || dateRange?.from) && (
                    <Button
                        variant="ghost"
                        className="text-muted-foreground hover:text-foreground h-9 ml-auto"
                        onClick={() => {
                            setUserEmailFilter(undefined);
                            setActionFilter(undefined);
                            setStatusFilter(undefined);
                            setDateRange(undefined);
                            setPage(1);
                        }}
                    >
                        <X className="h-4 w-4 mr-1" /> Сбросить все
                    </Button>
                )}
            </div>

            {/* Таблица */}
            {isLoading ? (
                <div className="text-center py-8 flex-1">Загрузка...</div>
            ) : items.length ? (
                <div className="w-full overflow-x-auto overflow-y-auto h-[calc(100dvh-420px)] rounded-md border relative">
                    <Table className="table-fixed w-full min-w-[800px]">
                        {/* ✅ Непрозрачный фон у заголовка */}
                        <TableHeader className="bg-background border-b sticky top-0 z-20 shadow-sm">
                            <TableRow className="hover:bg-transparent">
                                <TableHead className="w-[25%] font-semibold text-foreground">Пользователь</TableHead>
                                <TableHead className="w-[15%] font-semibold text-foreground">Действие</TableHead>
                                <TableHead className="w-[20%] font-semibold text-foreground">Ресурс</TableHead>
                                <TableHead className="w-[15%] font-semibold text-foreground">Статус</TableHead>
                                <TableHead className="w-[15%] font-semibold text-foreground">IP</TableHead>
                                <TableHead className="w-[10%] font-semibold text-foreground">Время</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody className={isFetching && !isLoading ? "opacity-60 transition-opacity" : ""}>
                            {items.map((log: any, index: number, array: any[]) => {
                                const currentDate = new Date(log.created_at).toLocaleDateString("ru-RU", {
                                    day: "numeric", month: "long", year: "numeric"
                                });
                                const prevDate = index > 0
                                    ? new Date(array[index - 1].created_at).toLocaleDateString("ru-RU", {
                                        day: "numeric", month: "long", year: "numeric"
                                    })
                                    : null;
                                const showDateHeader = currentDate !== prevDate;

                                return (
                                    <React.Fragment key={log.id}>
                                        {showDateHeader && (
                                            // ✅ Непрозрачный фон и z-10 (ниже заголовка)
                                            <TableRow className="bg-muted hover:bg-muted border-y sticky top-[37px] z-10 shadow-sm">
                                                <TableCell colSpan={6} className="py-2 px-4 font-semibold text-muted-foreground text-xs uppercase tracking-wider">
                                                    {currentDate}
                                                </TableCell>
                                            </TableRow>
                                        )}

                                        <TableRow>
                                            <TableCell className="align-top truncate" title={log.user_email || "Система"}>
                                                {log.user_email || "Система"}
                                            </TableCell>
                                            <TableCell className="align-top">
                                                {log.action === "login" ? (
                                                    <span className="flex items-center gap-1 text-green-600 font-medium">
                                                        <LogIn className="h-4 w-4" /> Вход
                                                    </span>
                                                ) : log.action === "logout" ? (
                                                    <span className="flex items-center gap-1 text-muted-foreground">
                                                        <LogOut className="h-4 w-4" /> Выход
                                                    </span>
                                                ) : log.action === "access_denied" ? (
                                                    <span className="flex items-center gap-1 text-red-600 font-medium">
                                                        <ShieldAlert className="h-4 w-4" /> Доступ запрещён
                                                    </span>
                                                ) : (
                                                    log.action
                                                )}
                                            </TableCell>
                                            <TableCell className="align-top truncate" title={log.resource}>
                                                {log.resource}
                                            </TableCell>
                                            <TableCell className="align-top">
                                                <Badge
                                                    variant={log.status === "success" ? "default" : "destructive"}
                                                    className={log.status === "success" ? "bg-green-600 text-white hover:bg-green-700" : ""}
                                                >
                                                    {log.status === "success" ? "Успешно" : "Ошибка"}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="align-top truncate">{log.ip_address}</TableCell>
                                            <TableCell className="align-top whitespace-nowrap text-xs">
                                                {new Date(log.created_at).toLocaleTimeString("ru-RU", { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                            </TableCell>
                                        </TableRow>
                                    </React.Fragment>
                                );
                            })}
                        </TableBody>
                    </Table>
                </div>
            ) : (
                <div className="flex flex-col items-center justify-center flex-1 text-muted-foreground">
                    <Search className="h-12 w-12 mb-4 opacity-20" />
                    <p className="text-lg font-medium">Логов не найдено</p>
                    <p className="text-sm">Попробуйте изменить параметры фильтра или периода</p>
                </div>
            )}

            {/* Пагинация */}
            <div className="shrink-0">
                <AuditPagination
                    page={page}
                    pageSize={pageSize}
                    total={total}
                    isFetching={isFetching}
                    jumpInput={jumpInput}
                    onPageChange={setPage}
                    onPageSizeChange={(val) => { setPageSize(Number(val)); setPage(1); }}
                    onJumpInputChange={setJumpInput}
                />
            </div>
        </div>
    );
};