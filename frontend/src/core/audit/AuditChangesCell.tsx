import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

const formatAuditValue = (val: any) => {
    if (val === null || val === undefined || val === "") return "пусто";
    if (Array.isArray(val)) {
        if (val.length === 0) return "пусто";
        return val.join(", ");
    }
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
};

export const AuditChangesCell = ({
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
                            <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0">
                                Удалено
                            </Badge>
                            <span className="text-muted-foreground break-words">
                                {trimmed.replace("[Удалено]", "").trim()}
                            </span>
                        </div>
                    );
                }
                if (trimmed.startsWith("[Добавлен]")) {
                    return (
                        <div key={idx} className="flex items-start gap-1 mb-1">
                            <Badge variant="default" className="bg-green-600 text-white text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0">
                                Добавлен
                            </Badge>
                            <span className="text-green-600 dark:text-green-400 font-medium break-words">
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
            <span className="text-green-600 dark:text-green-400 font-medium break-words">{text}</span>
        );
    };

    return (
        <div className="space-y-1 text-xs w-full">
            <div className="w-full space-y-1.5">
                {visibleEntries.map(([field, val]: [string, any]) => {
                    const oldVal = formatAuditValue(val?.old);
                    const newVal = formatAuditValue(val?.new);

                    const isNewEmpty = newVal === "пусто";
                    const isOldEmpty = oldVal === "пусто";

                    const showArrow = action === "update" && !isOldEmpty;

                    return (
                        <div
                            key={field}
                            // ✅ Используем border-border вместо border-gray-100
                            className="flex items-start gap-2 py-1 border-b border-border last:border-0 last:pb-0"
                        >
                            {/* Имя поля: ✅ text-foreground вместо text-gray-700 */}
                            <div className="font-semibold text-foreground w-[120px] shrink-0 break-words">
                                {field}:
                            </div>

                            {/* Старое значение: ✅ text-muted-foreground вместо text-gray-400 */}
                            {(action === "update" || action === "delete") && !isOldEmpty && (
                                <div className="text-muted-foreground text-[10px] w-[25%] shrink-0 break-words">
                                    {oldVal}
                                </div>
                            )}

                            {/* Стрелка: ✅ text-muted-foreground вместо text-gray-300 */}
                            {showArrow && (
                                <ArrowRight className="h-3 w-3 text-muted-foreground mt-0.5 shrink-0" />
                            )}

                            <div className="flex-1 break-words">
                                {action === "update" ? (
                                    isNewEmpty ? (
                                        <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4">
                                            Удалено
                                        </Badge>
                                    ) : (
                                        renderNewValue(newVal)
                                    )
                                ) : action === "create" ? (
                                    !isNewEmpty && renderNewValue(newVal)
                                ) : null}
                            </div>
                        </div>
                    );
                })}
            </div>

            {hasMore && (
                <Button
                    variant="link"
                    size="sm"
                    // ✅ Кнопка теперь использует muted-foreground (серый в светлой, светло-серый в темной)
                    className="text-xs h-6 px-0 text-muted-foreground hover:text-foreground mt-1 font-semibold"
                    onClick={() => setIsExpanded((v) => !v)}
                >
                    {isExpanded ? "Свернуть" : `Показать все (${entries.length - LIMIT})`}
                </Button>
            )}
        </div>
    );
};