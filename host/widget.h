#ifndef WIDGET_H
#define WIDGET_H

#include <QWidget>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTextEdit>
#include <QListWidget>
#include <QNetworkInterface>
#include <QHostAddress>
#include <QDateTime>
#include <QSqlDatabase>
#include <QSqlQuery>
#include <QSqlError>
#include <QDebug>
#include <QPixmap>
#include <QFileDialog>
#include <QThread>

#include "tcp_thread.h"
#include "udp_thread.h"

namespace Ui {
class Widget;
}

class Widget : public QWidget
{
    Q_OBJECT

public:
    explicit Widget(QWidget *parent = nullptr);
    ~Widget();

private slots:
    void on_btn_open_clicked();
    void on_btn_path_change_clicked();
    void on_selectBtn_clicked();
    void on_deleteButton_clicked();
    void on_addButton_clicked();
    void on_changeButton_clicked();
    void on_open_clicked();
    void on_close_clicked();
    void on_openButton_clicked();
    void on_closeButton_clicked();
    void display_udp_frame();
    void print_tcp_msg();
    void on_btn_send_clicked();
    void on_img_saved(const QString &path);

private:
    Ui::Widget *ui;
    Tcp_Thread *tcp_thread;
    Udp_Thread *udp_thread;

    void initDatabase();
    void storeMessage(const QString &msg);
    void close_thread();
    void is_ui_visiable(bool state);
    QHostAddress get_local_host_ip();
    void send_message(const QString &msg);
};

#endif // WIDGET_H
