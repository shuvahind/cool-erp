import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Loader2,
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
} from "lucide-react";

const PAGE_SIZE_OPTIONS: readonly number[] = [10, 15, 25, 50, 100];
const MAX_VISIBLE_PAGES = 7;
type PageItem = number | "gap-left" | "gap-right";

const buildPageItems = (current: number, total: number): PageItem[] => {
    if (total <= MAX_VISIBLE_PAGES) {
        return Array.from({ length: total }, (_, index) => index + 1);
    }
    const windowStart: number = Math.max(2, Math.min(current - 1, total - 4));
    const windowEnd: number = Math.min(total - 1, Math.max(current + 1, 5));

    const items: PageItem[] = [1];
    if (windowStart > 2) items.push("gap-left");
    for (let value = windowStart; value <= windowEnd; value += 1) {
        items.push(value);
    }
    if (windowEnd < total - 1) items.push("gap-right");
    items.push(total);
    return items;
};

interface AuditPaginationProps {
    page: number;
    pageSize: number;
    total: number;
    isFetching: boolean;
    jumpInput: string;
    onPageChange: (page: number) => void;
    onPageSizeChange: (size: string) => void;
    onJumpInputChange: (value: string) => void;
    // ❌ onJumpSubmit удалён
}

export const AuditPagination = ({
    page,
    pageSize,
    total,
    isFetching,
    jumpInput,
    onPageChange,
    onPageSizeChange,
    onJumpInputChange,
}: AuditPaginationProps) => {
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const currentPage = Math.min(page, totalPages);
    const isFirstPage = currentPage <= 1;
    const isLastPage = currentPage >= totalPages;

    const rangeStart = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const rangeEnd = Math.min(currentPage * pageSize, total);
    const pageItems = buildPageItems(currentPage, totalPages);

    // ✅ Валидация ввода
    const handleJumpSubmit = (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const parsed = parseInt(jumpInput, 10);
        if (isNaN(parsed)) {
            onJumpInputChange("");
            return;
        }
        const clamped = Math.min(Math.max(parsed, 1), totalPages);
        onPageChange(clamped);
        onJumpInputChange("");
    };

    return (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mt-4 pt-2 border-t">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {isFetching && <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />}
                <span className="tabular-nums">
                    {total === 0 ? (
                        "Нет записей"
                    ) : (
                        <>Показано <span className="font-medium text-foreground">{rangeStart}–{rangeEnd}</span> из <span className="font-medium text-foreground">{total}</span></>
                    )}
                </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <div className="flex items-center gap-2">
                    <span className="hidden sm:inline text-xs text-muted-foreground whitespace-nowrap">Строк на странице</span>
                    <Select value={String(pageSize)} onValueChange={onPageSizeChange}>
                        <SelectTrigger className="h-8 w-[72px] text-xs" aria-label="Строк на странице">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent position="popper" sideOffset={4} className="min-w-[72px]">
                            {PAGE_SIZE_OPTIONS.map((option) => (
                                <SelectItem key={option} value={String(option)} className="text-xs">{option}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <nav aria-label="Постраничная навигация" className="flex items-center gap-1">
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => onPageChange(1)} disabled={isFirstPage} title="Первая страница">
                        <ChevronsLeft className="h-4 w-4" />
                    </Button>
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => onPageChange(currentPage - 1)} disabled={isFirstPage} title="Предыдущая страница">
                        <ChevronLeft className="h-4 w-4" />
                    </Button>

                    {pageItems.map((item) =>
                        typeof item === "number" ? (
                            <Button key={item} variant={item === currentPage ? "default" : "ghost"} size="icon" className="h-8 min-w-8 px-1.5 text-xs tabular-nums" onClick={() => onPageChange(item)}>
                                {item}
                            </Button>
                        ) : (
                            <span key={item} className="flex h-8 w-6 items-center justify-center text-xs text-muted-foreground select-none">…</span>
                        ),
                    )}

                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => onPageChange(currentPage + 1)} disabled={isLastPage} title="Следующая страница">
                        <ChevronRight className="h-4 w-4" />
                    </Button>
                    <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => onPageChange(totalPages)} disabled={isLastPage} title="Последняя страница">
                        <ChevronsRight className="h-4 w-4" />
                    </Button>
                </nav>

                <form onSubmit={handleJumpSubmit} className="hidden lg:flex items-center gap-1.5">
                    <label htmlFor="audit-jump-page" className="text-xs text-muted-foreground whitespace-nowrap">Перейти</label>
                    <Input
                        id="audit-jump-page"
                        value={jumpInput}
                        onChange={(e) => onJumpInputChange(e.target.value.replace(/\D/g, ""))}
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder={String(currentPage)}
                        disabled={totalPages <= 1}
                        className="h-8 w-14 text-center text-xs tabular-nums"
                    />
                </form>
            </div>
        </div>
    );
};