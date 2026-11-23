import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { RefreshCw, Download, ShieldCheck } from "lucide-react";

interface AuditHeaderProps {
    activeTab: "access" | "data";
    onTabChange: (value: "access" | "data") => void;
    total: number;
    isFetching: boolean;
    onRefresh: () => void;
    onExport: () => void;
}

export const AuditHeader = ({
    activeTab,
    onTabChange,
    total,
    isFetching,
    onRefresh,
    onExport,
}: AuditHeaderProps) => {
    return (
        <div className="flex justify-between items-center shrink-0 gap-4 flex-wrap">
            <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-2">
                    <ShieldCheck className="h-7 w-7 text-primary" />
                    <h1 className="text-2xl font-bold">Аудит</h1>
                </div>

                <Tabs
                    value={activeTab}
                    onValueChange={(v) => onTabChange(v as "access" | "data")}
                >
                    <TabsList className="w-fit">
                        <TabsTrigger value="access">Логи входа</TabsTrigger>
                        <TabsTrigger value="data">Изменения данных</TabsTrigger>
                    </TabsList>
                </Tabs>

                <div className="hidden md:block text-sm text-muted-foreground">
                    Всего записей: {total}
                </div>
            </div>

            <div className="flex gap-2">
                <Button onClick={onRefresh} variant="outline" disabled={isFetching}>
                    <RefreshCw
                        className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`}
                    />
                    Обновить
                </Button>
                <Button onClick={onExport} variant="outline">
                    <Download className="h-4 w-4 mr-2" />
                    Экспорт
                </Button>
            </div>
        </div>
    );
};